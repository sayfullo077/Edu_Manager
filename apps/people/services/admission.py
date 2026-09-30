"""Use-case: o'quvchini qabul qilish (o'quvchi + vasiylar + shartnoma bitta tranzaksiyada) va vasiy biriktirish."""

import logging
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction

from .. import selectors
from ..models import Guardian, Student, StudentGuardian
from . import students as student_service

logger = logging.getLogger(__name__)

GUARDIAN_FIELDS = ("last_name", "first_name", "middle_name", "phone", "extra_phone", "passport", "pinfl",
                   "address", "workplace", "position", "status")


def _clean_guardian_data(data: dict) -> dict:
    return {k: v for k, v in data.items() if k in GUARDIAN_FIELDS and v not in (None,)}


def attach_guardian(student: Student, *, guardian_data: dict, relation: str, is_primary: bool, by
                    ) -> tuple[Guardian, bool]:
    """Ota-onani topadi (JSHSHIR yoki telefon+familiya) yoki yaratadi va o'quvchiga bog'laydi.

    Qaytaradi: (guardian, oldin_mavjud_edimi).
    """
    data = _clean_guardian_data(guardian_data)
    existing = selectors.find_existing_guardian(
        pinfl=data.get("pinfl", ""), phone=data.get("phone", ""), last_name=data.get("last_name", ""))

    with transaction.atomic():
        if existing:
            guardian = existing
            # Bo'sh maydonlarni yangi ma'lumot bilan to'ldiramiz, mavjudlarini ustiga yozmaymiz.
            changed = [f for f, v in data.items() if v and not getattr(guardian, f)]
            for f in changed:
                setattr(guardian, f, data[f])
            if changed:
                guardian.full_clean(exclude=["children"])
                guardian.save()
        else:
            guardian = Guardian(**data)
            guardian.full_clean(exclude=["children"])
            guardian.save()

        if StudentGuardian.objects.filter(student=student, guardian=guardian).exists():
            raise ValidationError("Bu ota-ona allaqachon shu o'quvchiga biriktirilgan.")
        if is_primary:
            StudentGuardian.objects.filter(student=student, is_primary=True).update(is_primary=False)
        elif not student.guardian_links.exists():
            is_primary = True  # birinchi ota-ona har doim asosiy aloqa
        StudentGuardian.objects.create(student=student, guardian=guardian, relation=relation,
                                       is_primary=is_primary)

    logger.info("Ota-ona biriktirildi: student=%s guardian=%s existed=%s (user=%s)",
                student.code, guardian.pk, bool(existing), by.pk)
    return guardian, bool(existing)


@dataclass(frozen=True)
class GuardianEntry:
    key: str  # formadagi o'rni: "father" | "mother" | "carrier"
    data: dict
    relation: str


@dataclass(frozen=True)
class FullAdmissionResult:
    student: Student
    contract: object
    reused_guardians: int  # tizimda oldindan bor bo'lib, biriktirilgan vasiylar soni


def admit_with_contract(*, branch, by, student_data: dict, guardians: list[GuardianEntry], signer: str,
                        contract_data: dict, academic_year) -> FullAdmissionResult:
    """Bitta qabul formasi: o'quvchi + vasiylar (Ota / Ona / Olib keluvchi) + shartnoma qoralamasi.

    Hammasi bitta tranzaksiyada — biror qism xato bo'lsa hech narsa saqlanmaydi. Xato `ProfileError`:
    `target` — "student", vasiy kaliti, "guardians", "signer" yoki "contract".
    Shartnoma tanlangan vasiy (`signer`) nomiga tuziladi — u asosiy aloqa bo'ladi (SMS kod unga boradi).
    """
    from apps.contracts.services import contracts as contract_service  # sikl importdan qochish

    if not guardians:
        raise ProfileError("guardians", ValidationError(
            "Kamida bitta vasiyni kiriting (Ota, Ona yoki olib keluvchi)."))
    if signer not in {g.key for g in guardians}:
        raise ProfileError("signer", ValidationError(
            {"signer": "Shartnoma vasiysi kiritilgan vasiylardan biri bo'lsin."}))
    school_class = student_data.get("school_class")
    if school_class and academic_year and school_class.academic_year_id != academic_year.pk:
        raise ProfileError("student", ValidationError(
            {"school_class": f"Sinf {academic_year.name} o'quv yiliga tegishli emas."}))

    ordered = sorted(guardians, key=lambda g: g.key != signer)  # asosiy vasiy birinchi biriktiriladi
    reused = 0
    with transaction.atomic():
        try:
            student = student_service.create_student(branch=branch, by=by, **student_data)
        except ValidationError as e:
            raise ProfileError("student", e) from e
        for entry in ordered:
            try:
                _, existed = attach_guardian(student, guardian_data=entry.data, relation=entry.relation,
                                             is_primary=entry.key == signer, by=by)
            except ValidationError as e:
                raise ProfileError(entry.key, e) from e
            reused += existed
        try:
            contract = contract_service.create_contract(student=student, by=by, academic_year=academic_year,
                                                        **contract_data)
        except ValidationError as e:
            raise ProfileError("contract", e) from e
    logger.info("Qabul: %s, %d vasiy, shartnoma %s (user=%s)", student.code, len(guardians), contract.number, by.pk)
    return FullAdmissionResult(student=student, contract=contract, reused_guardians=reused)


def update_guardian(guardian: Guardian, *, by, **data) -> Guardian:
    for field, value in _clean_guardian_data(data).items():
        setattr(guardian, field, value)
    guardian.full_clean(exclude=["children"])
    guardian.save()
    logger.info("Ota-ona tahrirlandi: %s (user=%s)", guardian.pk, by.pk)
    return guardian


class ProfileError(Exception):
    """Profilni saqlashdagi xato: `target` — qaysi forma ("student", vasiy havolasi pk'si yoki "new")."""

    def __init__(self, target, error: ValidationError):
        super().__init__(str(error))
        self.target, self.error = target, error


@dataclass(frozen=True)
class NewGuardian:
    data: dict
    relation: str


def update_profile(student: Student, *, by, student_data: dict, guardians: dict[int, dict],
                   new_guardian: NewGuardian | None = None) -> None:
    """O'quvchini tahrirlash sahifasi: o'quvchi, uning vasiylari va yangi vasiy — hammasi yoki hech biri.

    `guardians` — {havola_pk: ma'lumot}. Faqat shu o'quvchiga biriktirilgan vasiylar o'zgartiriladi.
    """
    links = {link.pk: link for link in student.guardian_links.select_related("guardian")}
    with transaction.atomic():
        try:
            student_service.update_student(student, by=by, **student_data)
        except ValidationError as e:
            raise ProfileError("student", e) from e
        for link_pk, data in guardians.items():
            link = links.get(link_pk)
            if link is None:
                continue
            try:
                update_guardian(link.guardian, by=by, **data)
            except ValidationError as e:
                raise ProfileError(link_pk, e) from e
        if new_guardian:
            try:
                attach_guardian(student, guardian_data=new_guardian.data, relation=new_guardian.relation,
                                is_primary=False, by=by)
            except ValidationError as e:
                raise ProfileError("new", e) from e


def detach_guardian(link: StudentGuardian, *, by) -> None:
    """Vasiyni o'quvchidan ajratish (vasiy yozuvi o'chirilmaydi — boshqa farzandlari bo'lishi mumkin).

    Asosiy aloqa ajratilmaydi: shartnoma va SMS unga bog'langan — avval boshqasini asosiy qiling.
    """
    if link.is_primary:
        raise ValidationError("Asosiy aloqadagi vasiyni ajratib bo'lmaydi — avval boshqa vasiyni asosiy qiling.")
    link.delete()
    logger.info("Vasiy ajratildi: student=%s guardian=%s (user=%s)", link.student_id, link.guardian_id, by.pk)


def set_primary(link: StudentGuardian, *, by) -> None:
    with transaction.atomic():
        StudentGuardian.objects.filter(student=link.student, is_primary=True).update(is_primary=False)
        StudentGuardian.objects.filter(pk=link.pk).update(is_primary=True)
    logger.info("Asosiy ota-ona: student=%s guardian=%s (user=%s)", link.student_id, link.guardian_id, by.pk)
