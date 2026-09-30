"""Yotoqxonaga joylashtirish va chiqarish."""

import logging
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import DormRoom, DormStay
from . import billing

logger = logging.getLogger(__name__)


@transaction.atomic
def check_in(*, student, room: DormRoom, on: date, by, note: str = "", monthly_fee=None) -> DormStay:
    """Qoidalar: o'quvchi faol va shu filialda, boshqa xonada yashamaydi, xona jinsi mos, bo'sh o'rin bor."""
    room = DormRoom.objects.select_for_update().get(pk=room.pk)  # bir vaqtda ikki joylashtirish sig'imni buzmasin
    if room.status != DormRoom.Status.ACTIVE:
        raise ValidationError({"room": f"Xona holati: {room.get_status_display().lower()} — joylashtirib bo'lmaydi."})
    if room.branch_id != student.branch_id:
        raise ValidationError({"room": "Xona boshqa filialga tegishli."})
    if student.status != student.Status.ACTIVE:
        raise ValidationError({"student": "Faqat faol o'quvchini joylashtirish mumkin."})
    if not room.accepts(student.gender):
        raise ValidationError({"room": f"«{room.name}» — {room.get_gender_display().lower()} uchun."})
    if DormStay.objects.filter(student=student, checked_out__isnull=True).exists():
        raise ValidationError({"student": "O'quvchi allaqachon yotoqxonada yashayapti."})
    if room.stays.filter(checked_out__isnull=True).count() >= room.capacity:
        raise ValidationError({"room": f"«{room.name}» da bo'sh o'rin yo'q."})
    fee = room.monthly_fee if monthly_fee is None else monthly_fee
    if fee < 0:
        raise ValidationError({"monthly_fee": "Oylik to'lov manfiy bo'lmaydi."})
    stay = DormStay.objects.create(student=student, room=room, checked_in=on, monthly_fee=fee,
                                   note=note.strip()[:255], created_by=by)
    billing.generate_for_stay(stay, through=timezone.localdate())
    logger.info("Yotoqxona: %s → %s (%s) (user=%s)", student.code, room.name, on, by.pk)
    return stay


@transaction.atomic
def check_out(stay: DormStay, *, on: date, by) -> DormStay:
    stay = DormStay.objects.select_for_update().get(pk=stay.pk)
    if stay.checked_out:
        raise ValidationError("O'quvchi allaqachon chiqqan.")
    if on < stay.checked_in:
        raise ValidationError({"on": "Chiqish sanasi kirgan sanadan oldin bo'lmaydi."})
    stay.checked_out = on
    stay.save(update_fields=["checked_out", "updated_at"])
    billing.generate_for_stay(stay, through=on)  # chiqqan oygacha bo'shliq qolmasin
    billing.close_for_stay(stay)
    logger.info("Yotoqxonadan chiqdi: %s (%s) (user=%s)", stay.student.code, on, by.pk)
    return stay
