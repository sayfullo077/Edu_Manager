"""Jarimalar: qo'shish va bekor qilish (moliyaviy yozuv — o'chirilmaydi)."""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.people.models import Teacher

from ..models import Penalty


def add_penalty(*, branch, teacher: Teacher, month: date, amount: Decimal, reason: str, by) -> Penalty:
    if teacher.branch_id != branch.pk:
        raise ValidationError("O'qituvchi bu filialda emas.")
    if amount <= 0:
        raise ValidationError("Summa musbat bo'lishi kerak.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Sababini yozing.")
    return Penalty.objects.create(branch=branch, teacher=teacher, month=month.replace(day=1), amount=amount,
                                  reason=reason, created_by=by)


@transaction.atomic
def cancel_penalty(penalty: Penalty, *, reason: str, by) -> Penalty:
    penalty = Penalty.objects.select_for_update().get(pk=penalty.pk)
    if penalty.cancelled_at:
        raise ValidationError("Jarima allaqachon bekor qilingan.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Bekor qilish sababini yozing.")
    penalty.cancelled_at, penalty.cancelled_by, penalty.cancel_reason = timezone.now(), by, reason
    penalty.save(update_fields=["cancelled_at", "cancelled_by", "cancel_reason", "updated_at"])
    return penalty
