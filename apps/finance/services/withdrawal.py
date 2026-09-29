"""O'quvchining o'qishdan chiqishi: yakuniy hisob-kitob.

Qoidalar:
- Chiqish oyidan oldingi oylar o'zgarmaydi.
- Chiqish oyi: faqat o'qigan kunlar — `oylik × o'qigan_kunlar / oy_kunlari`, INVOICE_ROUNDING ga pastga
  yaxlitlanadi (qabuldagi proratsiya bilan bir xil). O'qigan kunlar oy boshidan (yoki shartnoma boshlanishidan)
  chiqish sanasigacha, shu kun ham kiradi. Mavjud summadan oshmaydi.
- Keyingi oylar bekor qilinadi.
- Yotoqxona grafigi (bo'lsa) o'zining chiqish sanasi bilan xuddi shunday hisoblanadi.
- To'langan pul oylarga qaytadan eng eski oydan (FIFO) taqsimlanadi; ortgani qaytariladi (REFUND chiqimi),
  yetmagani qarz bo'lib grafikda qoladi.
- Hammasi bitta tranzaksiyada; `Withdrawal` + `WithdrawalLine` — audit, o'chirilmaydi.
"""

import calendar
import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_FLOOR, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.common.templatetags.ui import money
from apps.contracts.models import Contract
from apps.people.models import Student

from ..models import Account, Invoice, Transaction, Withdrawal, WithdrawalLine
from . import cash, ledger

logger = logging.getLogger(__name__)
security_log = logging.getLogger("security")
ZERO = Decimal("0")

REFUND_ACCOUNT = {Withdrawal.RefundMethod.CASH: Account.Kind.CASH,
                  Withdrawal.RefundMethod.TRANSFER: Account.Kind.BANK}


@dataclass
class Line:
    invoice: Invoice
    new_amount: Decimal
    new_paid: Decimal = ZERO

    @property
    def changed(self) -> bool:
        return self.new_amount != self.invoice.amount or self.new_paid != self.invoice.paid

    @property
    def kind(self) -> str:
        """Jadval uchun: "kept" (o'zgarmaydi), "partial" (chiqish oyi), "cancelled" (keyingi oy)."""
        if self.new_amount == 0:
            return "cancelled"
        return "partial" if self.new_amount != self.invoice.amount else "kept"


@dataclass
class Settlement:
    left_on: date
    dorm_left_on: date | None
    lines: list[Line] = field(default_factory=list)
    charged: Decimal = ZERO
    paid: Decimal = ZERO
    refund: Decimal = ZERO
    debt: Decimal = ZERO
    has_dorm: bool = False


def _round(value: Decimal) -> Decimal:
    step = Decimal(settings.INVOICE_ROUNDING)
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def month_charge(invoice: Invoice, left_on: date) -> Decimal:
    """Chiqish sanasi bo'yicha shu oy grafigining yangi summasi."""
    month, left_month = invoice.month, left_on.replace(day=1)
    if month < left_month:
        return invoice.amount
    if month > left_month:
        return ZERO
    monthly_fee = invoice.full_amount - invoice.discount
    start = month
    if invoice.contract_id and invoice.contract.start_date > month:
        start = invoice.contract.start_date  # oy o'rtasida kelgan (birinchi oy)
    days = (left_on - start).days + 1
    if days <= 0:
        return ZERO
    days_in_month = calendar.monthrange(month.year, month.month)[1]
    return min(invoice.amount, _round(Decimal(monthly_fee) * days / days_in_month))


def _validate(student, left_on: date, dorm_left_on: date | None) -> None:
    if Withdrawal.objects.filter(student_id=student.pk).exists():  # hasattr() eskirgan keshni ko'rishi mumkin
        raise ValidationError("Bu o'quvchi uchun chiqish hisob-kitobi allaqachon rasmiylashtirilgan.")
    errors = {}
    today = timezone.localdate()
    if left_on > today:
        errors["left_on"] = "Chiqish sanasi kelajakda bo'lishi mumkin emas."
    elif left_on < student.joined_at:
        errors["left_on"] = "Chiqish sanasi qabul qilingan sanadan oldin bo'lishi mumkin emas."
    if dorm_left_on and dorm_left_on > left_on:
        errors["dorm_left_on"] = "Yotoqxonadan chiqish maktabdan chiqishdan keyin bo'lmaydi."
    if errors:
        raise ValidationError(errors)


def calculate(student, *, left_on: date, dorm_left_on: date | None = None, invoices=None) -> Settlement:
    """Hisob-kitobni hisoblaydi, hech narsa saqlamaydi (ko'rib chiqish sahifasi uchun)."""
    _validate(student, left_on, dorm_left_on)
    if invoices is None:
        invoices = (student.invoices.exclude(status=Invoice.Status.CANCELLED)
                    .select_related("contract").order_by("month", "category"))
    result = Settlement(left_on=left_on, dorm_left_on=dorm_left_on)
    for invoice in invoices:
        is_dorm = invoice.category == Invoice.Category.DORM
        result.has_dorm |= is_dorm
        result.lines.append(Line(invoice, month_charge(invoice, (dorm_left_on or left_on) if is_dorm else left_on)))

    result.charged = sum((ln.new_amount for ln in result.lines), ZERO)
    result.paid = sum((ln.invoice.paid for ln in result.lines), ZERO)
    kept = min(result.paid, result.charged)
    left = kept
    for ln in result.lines:  # to'langan pul eng eski oydan qayta taqsimlanadi
        ln.new_paid = min(left, ln.new_amount)
        left -= ln.new_paid
    result.refund = result.paid - kept
    result.debt = result.charged - kept
    return result


@transaction.atomic
def withdraw(student, *, left_on: date, reason: str, by, dorm_left_on: date | None = None, note: str = "",
             refund_method: str = "", expected_refund: Decimal | None = None) -> Withdrawal:
    """Hisob-kitobni rasmiylashtiradi: grafik, pul qaytarish, shartnoma yopiladi, o'quvchi «Ketgan»."""
    student = Student.objects.select_for_update().get(pk=student.pk)
    invoices = list(student.invoices.select_for_update(of=("self",)).exclude(status=Invoice.Status.CANCELLED)
                    .select_related("contract").order_by("month", "category"))
    plan = calculate(student, left_on=left_on, dorm_left_on=dorm_left_on, invoices=invoices)
    if expected_refund is not None and expected_refund != plan.refund:
        raise ValidationError("Hisob-kitob ko'rib chiqilgandan keyin o'zgardi (yangi to'lov yoki storno). "
                              "Qayta ko'rib chiqing.")
    if reason not in Withdrawal.Reason.values:
        raise ValidationError({"reason": "Chiqish sababini tanlang."})

    account = session = None
    if plan.refund > 0:
        if refund_method not in REFUND_ACCOUNT:
            raise ValidationError({"refund_method": "Pulni qaytarish usulini tanlang."})
        account = ledger.get_account(student.branch, REFUND_ACCOUNT[refund_method])
        if refund_method == Withdrawal.RefundMethod.CASH:
            session = cash.require_open_session(student.branch)
            available = ledger.balance(account)
            if available < plan.refund:
                raise ValidationError({"refund_method": f"Kassada yetarli naqd yo'q: {money(available)} so'm."})
    else:
        refund_method = ""

    record = Withdrawal.objects.create(
        branch=student.branch, student=student, left_on=left_on, dorm_left_on=dorm_left_on if plan.has_dorm else None,
        reason=reason, note=note.strip()[:255], charged=plan.charged, paid=plan.paid, refund=plan.refund,
        debt=plan.debt, refund_method=refund_method, account=account, cash_session=session, created_by=by)

    for ln in plan.lines:
        invoice = ln.invoice
        WithdrawalLine.objects.create(withdrawal=record, invoice=invoice, old_amount=invoice.amount,
                                      new_amount=ln.new_amount, old_paid=invoice.paid, new_paid=ln.new_paid)
        if not ln.changed:
            continue
        invoice.waived += invoice.amount - ln.new_amount
        invoice.amount, invoice.paid = ln.new_amount, ln.new_paid
        if ln.new_amount == 0:
            invoice.status = Invoice.Status.CANCELLED
        else:
            invoice.refresh_status()
        invoice.save(update_fields=["amount", "waived", "paid", "status", "updated_at"])

    if plan.refund > 0:
        ledger.record(account=account, direction=Transaction.Direction.OUT, kind=Transaction.Kind.REFUND,
                      amount=plan.refund, by=by, occurred_at=timezone.now(), withdrawal=record,
                      description=f"Qaytarildi: {student.short_name} — {record.number}")

    now = timezone.now()
    label = Withdrawal.Reason(reason).label
    (Contract.objects.filter(student=student).exclude(status=Contract.Status.CANCELLED)
     .update(status=Contract.Status.CANCELLED, cancelled_at=now,
             cancel_reason=f"O'qishdan chiqdi {left_on:%d.%m.%Y}: {label} ({record.number})"))
    # Maktab chetlatgan bo'lsa — "O'qishdan chiqarilgan", qolgan hollarda — "Ketgan"
    student.status = Student.Status.EXPELLED if reason == Withdrawal.Reason.EXPELLED else Student.Status.LEFT
    student.left_at = left_on
    student.save(update_fields=["status", "left_at", "updated_at"])

    security_log.warning("O'qishdan chiqish: %s %s qaytarildi=%s qarz=%s (user=%s)",
                         record.number, student.code, plan.refund, plan.debt, by.pk)
    return record
