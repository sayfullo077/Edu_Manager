"""Shartnoma use-case'lari. Holat o'tishlari faqat shu yerda: draft → sent → signed, istalgan → cancelled."""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.domain.exceptions import OTPError
from apps.accounts.models import OneTimeCode
from apps.accounts.services import otp
from apps.common import ratelimit
from apps.common.templatetags.ui import money
from apps.core.models import AcademicYear, SchoolSettings
from apps.finance.services import invoices
from apps.people.models import Student

from ..models import Contract

logger = logging.getLogger(__name__)
security_log = logging.getLogger("security")

EDITABLE_FIELDS = ("full_tariff", "discount_percent", "discount_reason", "start_date", "end_date", "notes")


@dataclass(frozen=True)
class ContractDefaults:
    full_tariff: Decimal
    start_date: date
    end_date: date


def defaults_for(student: Student) -> ContractDefaults:
    """Yangi shartnoma uchun tavsiya: sinf tarifi va joriy o'quv yili (yoki qabul sanasidan)."""
    year = AcademicYear.current()
    tariff = student.school_class.monthly_tariff if student.school_class else Decimal("0")
    start = max(student.joined_at, year.start_date) if year else student.joined_at
    end = year.end_date if year else date(start.year + 1, 6, 30)
    return ContractDefaults(full_tariff=tariff, start_date=start, end_date=end)


def _primary_guardian(student: Student):
    link = student.guardian_links.select_related("guardian").filter(is_primary=True).first()
    if link is None:
        raise ValidationError("O'quvchiga asosiy aloqa (ota-ona) biriktirilmagan.")
    return link.guardian


def _validate(contract: Contract, year: AcademicYear) -> None:
    errors = {}
    if not (year.start_date <= contract.start_date <= year.end_date):
        errors["start_date"] = f"Sana {year.name} o'quv yili ichida bo'lishi kerak."
    if contract.end_date <= contract.start_date:
        errors["end_date"] = "Tugash sanasi boshlanishdan keyin bo'lishi kerak."
    if contract.discount_percent and not contract.discount_reason:
        errors["discount_reason"] = "Chegirma berilsa, sababini yozing (audit uchun)."
    if errors:
        raise ValidationError(errors)


def create_contract(*, student: Student, by, **data) -> Contract:
    if student.status != Student.Status.ACTIVE:
        raise ValidationError("Faqat faol o'quvchi bilan shartnoma tuziladi.")
    year = AcademicYear.current()
    if year is None:
        raise ValidationError("Joriy o'quv yili belgilanmagan (admin panel → O'quv yillari).")
    contract = Contract(
        branch=student.branch, academic_year=year, student=student, guardian=_primary_guardian(student),
        class_name=student.school_class.name if student.school_class else "", created_by=by,
        **{k: v for k, v in data.items() if k in EDITABLE_FIELDS})
    _validate(contract, year)
    try:
        with transaction.atomic():
            contract.save()
    except IntegrityError as e:
        raise ValidationError("Bu o'quvchining joriy o'quv yili uchun amaldagi shartnomasi bor.") from e
    logger.info("Shartnoma tuzildi: %s student=%s (user=%s)", contract.number, student.code, by.pk)
    return contract


def update_contract(contract: Contract, *, by, **data) -> Contract:
    if not contract.is_editable:
        raise ValidationError("Faqat qoralama holatidagi shartnomani tahrirlash mumkin.")
    for field, value in data.items():
        if field in EDITABLE_FIELDS:
            setattr(contract, field, value)
    _validate(contract, contract.academic_year)
    contract.save()
    logger.info("Shartnoma tahrirlandi: %s (user=%s)", contract.number, by.pk)
    return contract


def send_confirmation_code(contract: Contract, *, by, ip: str) -> None:
    """Ota-onaga SMS kod yuboradi. Kod faqat shu shartnoma uchun amal qiladi."""
    if contract.status not in (Contract.Status.DRAFT, Contract.Status.SENT):
        raise ValidationError("Bu shartnomaga kod yuborib bo'lmaydi.")
    ratelimit.enforce("contract_code_ip", ip)
    ratelimit.enforce("contract_code_phone", contract.guardian.phone)
    try:
        otp.issue_code(
            contract.guardian.phone, OneTimeCode.Purpose.CONTRACT, SchoolSettings.load().short_name,
            subject=contract.otp_subject,
            extra={"student": contract.student.short_name, "number": contract.number,
                   # Oddiy probel: NBSP GSM-7 alifbosida yo'q → SMS Unicode'ga o'tib, narxi oshadi.
                   "fee": money(contract.monthly_fee).replace("\u00a0", " ")})
    except OTPError as e:
        raise ValidationError(str(e)) from e
    if contract.status == Contract.Status.DRAFT:
        Contract.objects.filter(pk=contract.pk).update(status=Contract.Status.SENT, sent_at=timezone.now())
        contract.refresh_from_db()
    logger.info("Shartnoma kodi yuborildi: %s (user=%s)", contract.number, by.pk)


def confirm_with_code(contract: Contract, *, code: str, by, ip: str) -> Contract:
    if contract.status != Contract.Status.SENT:
        raise ValidationError("Avval ota-onaga tasdiqlash kodini yuboring.")
    ratelimit.enforce("otp_verify_ip", ip)
    try:
        otp.verify_code(contract.guardian.phone, OneTimeCode.Purpose.CONTRACT, code, subject=contract.otp_subject)
    except OTPError as e:
        security_log.info("Shartnoma kodi xato: %s ip=%s", contract.number, ip)
        raise ValidationError({"code": str(e)}) from e
    with transaction.atomic():
        updated = Contract.objects.filter(pk=contract.pk, status=Contract.Status.SENT).update(
            status=Contract.Status.SIGNED, signed_at=timezone.now(), signed_phone=contract.guardian.phone)
        contract.refresh_from_db()
        if updated:  # parallel so'rov ikkinchi marta grafik yaratmasin
            invoices.generate_for_contract(contract, through=timezone.localdate())  # qolgani — oyma-oy
    logger.info("Shartnoma imzolandi: %s (user=%s)", contract.number, by.pk)
    return contract


def cancel_contract(contract: Contract, *, reason: str, by) -> Contract:
    if contract.status == Contract.Status.CANCELLED:
        raise ValidationError("Shartnoma allaqachon bekor qilingan.")
    if not reason.strip():
        raise ValidationError({"reason": "Bekor qilish sababini yozing."})
    today = timezone.localdate()
    next_month = date(today.year + (today.month == 12), today.month % 12 + 1, 1)
    with transaction.atomic():
        Contract.objects.filter(pk=contract.pk).update(
            status=Contract.Status.CANCELLED, cancelled_at=timezone.now(), cancel_reason=reason.strip())
        contract.refresh_from_db()
        # Joriy oy qarzi qoladi; keyingi oylarning to'lanmagan grafiklari bekor qilinadi.
        invoices.cancel_unpaid_for_contract(contract, from_month=max(next_month, contract.start_date))
    logger.warning("Shartnoma bekor qilindi: %s sabab=%r (user=%s)", contract.number, reason, by.pk)
    return contract


def attach_scan(contract: Contract, *, file, by) -> Contract:
    if contract.status == Contract.Status.CANCELLED:
        raise ValidationError("Bekor qilingan shartnomaga fayl biriktirilmaydi.")
    if contract.scan:
        contract.scan.delete(save=False)
    contract.scan = file
    contract.full_clean(exclude=["created_by", "guardian", "student", "branch", "academic_year"])
    contract.save(update_fields=["scan", "updated_at"])
    logger.info("Shartnoma skaneri yuklandi: %s (user=%s)", contract.number, by.pk)
    return contract
