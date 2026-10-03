"""Yotoqxona davomatini belgilash (Zavuch)."""

from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ..models import DormAttendance, DormStay


def _stay_on(branch, student_id: int, day: date) -> DormStay:
    stay = (DormStay.objects.filter(room__branch=branch, student_id=student_id, checked_in__lte=day)
            .filter(Q(checked_out__isnull=True) | Q(checked_out__gte=day)).first())
    if stay is None:
        raise ValidationError("Bu kuni o'quvchi yotoqxonada yashamagan.")
    return stay


def _check_day(day: date) -> None:
    if day > timezone.localdate():
        raise ValidationError("Kelgusi kun uchun davomat belgilanmaydi.")


@transaction.atomic
def mark(*, branch, student_id: int, day: date, status: str, by) -> DormAttendance | None:
    """Bitta katak. Bo'sh `status` — belgini olib tashlash («belgilanmagan»)."""
    _check_day(day)
    stay = _stay_on(branch, student_id, day)
    if not status:
        DormAttendance.objects.filter(student_id=student_id, date=day).delete()
        return None
    if status not in DormAttendance.Status.values:
        raise ValidationError("Belgi noto'g'ri.")
    obj, _ = DormAttendance.objects.update_or_create(
        student_id=student_id, date=day, defaults={"stay": stay, "status": status, "marked_by": by})
    return obj


@transaction.atomic
def mark_day(*, branch, day: date, marks: dict[int, str], by) -> int:
    """«Kunlik belgilash»: {student_id: status}. Qaytaradi — saqlangan belgilar soni."""
    _check_day(day)
    saved = 0
    for student_id, status in marks.items():
        mark(branch=branch, student_id=student_id, day=day, status=status, by=by)
        saved += bool(status)
    return saved
