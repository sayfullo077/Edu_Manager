"""Sinf davomati: sinf rahbari kunlik belgilaydi (bo'sh → keldi → kelmadi → kechikdi → sababli)."""

from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.people.models import Student

from ..models import ClassAttendance, SchoolClass


@transaction.atomic
def save_day(school_class: SchoolClass, *, day: date, rows: dict[int, tuple[str, str]], by) -> int:
    """rows: {student_id: (status, note)}. Bo'sh belgi va bo'sh izoh — yozuv olib tashlanadi.

    Qaytaradi: saqlangan belgilar soni.
    """
    if day > timezone.localdate():
        raise ValidationError("Kelgusi kun uchun davomat kiritilmaydi.")
    allowed = set(Student.objects.filter(school_class=school_class, pk__in=rows.keys()).values_list("pk", flat=True))
    saved = 0
    for student_id, (status, note) in rows.items():
        if student_id not in allowed:
            raise ValidationError("O'quvchi bu sinfda emas.")
        note = (note or "").strip()[:255]
        if status and status not in ClassAttendance.Status.values:
            raise ValidationError("Belgi noto'g'ri.")
        if not status:
            if note:
                raise ValidationError("Izoh yozilgan o'quvchiga belgi qo'ying (masalan, «Sababli»).")
            ClassAttendance.objects.filter(student_id=student_id, date=day).delete()
            continue
        ClassAttendance.objects.update_or_create(
            student_id=student_id, date=day,
            defaults={"school_class": school_class, "status": status, "note": note, "marked_by": by})
        saved += 1
    return saved
