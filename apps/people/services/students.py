"""O'quvchilar bilan bog'liq use-case'lar."""

import logging
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.domain.phone import format_phone

from .. import selectors
from ..models import Student
from . import address

logger = logging.getLogger(__name__)

EDITABLE_FIELDS = (
    "last_name", "first_name", "middle_name", "birth_date", "gender", "phone",
    "passport", "pinfl", "birth_certificate", "region", "district", "mahalla", "address",
    "grade", "school_class", "status", "in_erp", "in_emaktab", "joined_at", "left_at", "notes",
)
FLAG_FIELDS = ("in_erp", "in_emaktab")


def _validate(student: Student) -> None:
    errors = {}
    if student.school_class and student.school_class.branch_id != student.branch_id:
        errors["school_class"] = "Sinf boshqa filialga tegishli."
    sc = student.school_class
    if sc and sc.kind == sc.Kind.REGULAR and sc.grade and sc.grade != student.grade:
        errors["grade"] = f"«{sc.name}» sinfi {sc.grade}-sinf, o'quvchi darajasi mos emas."
    today = date.today()
    if student.birth_date and not (today.year - 20 <= student.birth_date.year <= today.year - 4):
        errors["birth_date"] = "Tug'ilgan sana maktab yoshiga mos emas."
    if student.status in Student.GONE_STATUSES and not student.left_at:
        student.left_at = today
    if errors:
        raise ValidationError(errors)


@transaction.atomic
def create_student(*, branch, by, **data) -> Student:
    student = Student(branch=branch, **{k: v for k, v in data.items() if k in EDITABLE_FIELDS})
    _validate(student)
    student.save()  # kod (STD-YYYY-NNN) shu yerda beriladi
    address.remember_mahalla(region=student.region, district=student.district, mahalla=student.mahalla)
    logger.info("O'quvchi qo'shildi: %s (user=%s)", student.code, by.pk)
    return student


@transaction.atomic
def update_student(student: Student, *, by, **data) -> Student:
    for field, value in data.items():
        if field in EDITABLE_FIELDS:
            setattr(student, field, value)
    _validate(student)
    student.save()
    address.remember_mahalla(region=student.region, district=student.district, mahalla=student.mahalla)
    logger.info("O'quvchi tahrirlandi: %s (user=%s)", student.code, by.pk)
    return student


EXPORT_LIMIT = 10_000
EXPORT_HEADERS = ["#", "Kodi", "Familiya", "Ism", "Otasining ismi", "Sinf", "Daraja", "Jinsi", "Tug'ilgan sana",
                  "Telefon", "Manzil", "Holati", "Qabul qilingan", "ERP", "E-maktab"]


def export_rows(qs):
    """Jadval qatorlari (Excel uchun). Passport/JSHSHIR kabi maxfiy maydonlar eksport qilinmaydi."""
    yes_no = {True: "Ha", False: "Yo'q"}
    for i, s in enumerate(qs[:EXPORT_LIMIT], start=1):
        yield [i, s.code, s.last_name, s.first_name, s.middle_name,
               s.school_class.name if s.school_class else "", s.grade, s.get_gender_display(),
               s.birth_date, format_phone(s.phone) if s.phone else "", s.address, s.get_status_display(),
               s.joined_at, yes_no[s.in_erp], yes_no[s.in_emaktab]]


@transaction.atomic
def remove_student(student: Student, *, by) -> str:
    """O'quvchini o'chirish so'rovi. Natija:

    - "deleted" — hech qanday tarixi yo'q (xato kiritilgan), butunlay o'chirildi;
    - "needs_settlement" — to'lov grafigi yoki to'lovi bor: avval o'qishdan chiqarish hisob-kitobi kerak
      (o'qigan kunlar hisoblanadi, ortiqcha pul qaytariladi) — hech narsa o'zgartirilmaydi;
    - "archived" — tarixi bor (hisob-kitob qilingan yoki faqat qoralama shartnoma): «Ketgan» holatida qoladi.
    """
    if selectors.needs_settlement(student):
        return "needs_settlement"
    if selectors.student_has_history(student):
        if student.status != Student.Status.LEFT:
            student.status = Student.Status.LEFT
            student.left_at = student.left_at or date.today()
            student.save(update_fields=["status", "left_at", "updated_at"])
        logger.info("O'quvchi arxivlandi: %s (user=%s)", student.code, by.pk)
        return "archived"
    code = student.code
    student.delete()
    logger.info("O'quvchi o'chirildi: %s (user=%s)", code, by.pk)
    return "deleted"


def toggle_flag(student: Student, field: str, *, by) -> bool:
    if field not in FLAG_FIELDS:
        raise ValueError(field)
    value = not getattr(student, field)
    Student.objects.filter(pk=student.pk).update(**{field: value})
    logger.info("O'quvchi %s: %s=%s (user=%s)", student.code, field, value, by.pk)
    return value
