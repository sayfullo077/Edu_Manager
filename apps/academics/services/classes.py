"""Sinflar: yaratish, tahrirlash, o'chirish (tarixi bo'lsa — faolsizlantirish)."""

import logging

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.people.models import Student, Teacher

from ..models import SchoolClass

logger = logging.getLogger(__name__)

FIELDS = ("academic_year", "name", "kind", "grade", "language", "homeroom_teacher", "room", "capacity",
          "monthly_tariff", "is_active")


def _validate(c: SchoolClass) -> None:
    errors = {}
    c.name = " ".join((c.name or "").split())
    if c.kind == SchoolClass.Kind.REGULAR and not c.grade:
        errors["grade"] = "Oddiy sinf uchun darajani kiriting (1–11)."
    if c.kind == SchoolClass.Kind.DIRECTION:
        c.grade = None  # yo'nalishda turli sinf o'quvchilari aralash
    t = c.homeroom_teacher
    if t and (t.branch_id != c.branch_id or t.status in Teacher.NOT_WORKING):
        errors["homeroom_teacher"] = "Sinf rahbari shu filialning faol o'qituvchisi bo'lishi kerak."
    if c.room and c.room.branch_id != c.branch_id:
        errors["room"] = "Xona boshqa filialga tegishli."
    if c.pk:
        n = c.students.filter(status=Student.Status.ACTIVE).count()
        if c.capacity < n:
            errors["capacity"] = f"Sinfda hozir {n} nafar faol o'quvchi bor — sig'im undan kam bo'lmasin."
        if c.kind == SchoolClass.Kind.REGULAR and c.grade and \
                c.students.filter(status=Student.Status.ACTIVE).exclude(grade=c.grade).exists():
            errors["grade"] = "Sinfdagi o'quvchilar darajasi boshqa — avval o'quvchilarni ko'chiring."
    if errors:
        raise ValidationError(errors)


def save_class(instance: SchoolClass | None, *, branch, by, **data) -> SchoolClass:
    c = instance or SchoolClass(branch=branch)
    for field in FIELDS:
        if field in data:
            setattr(c, field, data[field])
    _validate(c)
    try:
        with transaction.atomic():
            c.save()
    except IntegrityError as e:
        raise ValidationError({"name": f"«{c.name}» nomli sinf bu o'quv yilida bor."}) from e
    logger.info("Sinf %s: %s (user=%s)", "tahrirlandi" if instance else "yaratildi", c.name, by.pk)
    return c


def delete_class(c: SchoolClass, *, by) -> str:
    """O'quvchi yoki guruhi bo'lgan sinf o'chirilmaydi — faolsizlantiriladi (tarix saqlanadi).

    Qaytaradi: "deleted" | "deactivated".
    """
    if c.students.exists() or c.groups.exists():
        c.is_active = False
        c.save(update_fields=["is_active", "updated_at"])
        logger.info("Sinf faolsizlantirildi: %s (user=%s)", c.name, by.pk)
        return "deactivated"
    c.delete()
    logger.info("Sinf o'chirildi: %s (user=%s)", c.name, by.pk)
    return "deleted"
