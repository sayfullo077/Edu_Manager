"""Use-case: o'quvchini qabul qilish (o'quvchi + ota-ona bitta tranzaksiyada) va ota-ona biriktirish."""

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


@dataclass(frozen=True)
class AdmissionResult:
    student: Student
    guardian: Guardian
    guardian_existed: bool


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


@transaction.atomic
def admit_student(*, branch, student_data: dict, guardian_data: dict, relation: str, by) -> AdmissionResult:
    """Yangi o'quvchini qabul qilish. Biror qadam xato bo'lsa hech narsa saqlanmaydi."""
    student = student_service.create_student(branch=branch, by=by, **student_data)
    guardian, existed = attach_guardian(student, guardian_data=guardian_data, relation=relation,
                                        is_primary=True, by=by)
    return AdmissionResult(student=student, guardian=guardian, guardian_existed=existed)


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
