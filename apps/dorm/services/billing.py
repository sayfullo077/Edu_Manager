"""Yotoqxona to'lov grafigi (Invoice, category=DORM) — yashash qaydidan oyma-oy.

- Kirgan oy: o'qishdagi kabi proratsiya (oyning 1–5-kuni kelsa to'liq oy) — `invoices.first_month_amount`.
- Chiqqan oy: faqat yashagan kunlar (`oylik × kunlar / oy_kunlari`, mingga pastga), to'langandan kam bo'lmaydi.
- Chiqqandan keyingi to'lanmagan oylar bekor qilinadi; oldindan to'langan oylar saqlanadi (qaytarish — alohida qaror).
- "Jami" (full_amount) — xona narxi; o'quvchi narxi kam bo'lsa farq — chegirma (discount).
"""

import calendar
import logging
from datetime import date, timedelta
from decimal import ROUND_FLOOR, Decimal

from django.conf import settings
from django.db import transaction

from apps.finance.models import Invoice
from apps.finance.services import invoices as invoice_service

from ..models import DormStay

logger = logging.getLogger(__name__)


def _round(value: Decimal) -> Decimal:
    step = Decimal(settings.INVOICE_ROUNDING)
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def _last_month_amount(fee: Decimal, month: date, start: date, end: date) -> Decimal:
    """Chiqqan oy uchun yashagan kunlar (kirgan kun ham, chiqqan kun ham kiradi)."""
    first_day = max(month, start)
    days = (end - first_day).days + 1
    days_in_month = calendar.monthrange(month.year, month.month)[1]
    return _round(Decimal(fee) * max(days, 0) / days_in_month)


def _month_amount(stay: DormStay, month: date) -> Decimal:
    fee = stay.monthly_fee
    amount = invoice_service.first_month_amount(fee, stay.checked_in) if month == stay.checked_in.replace(day=1) \
        else fee
    if stay.checked_out and month == stay.checked_out.replace(day=1):
        amount = min(amount, _last_month_amount(fee, month, stay.checked_in, stay.checked_out))
    return amount


def _due_date(stay: DormStay, month: date) -> date:
    due = invoice_service.due_date_for(month)
    if month == stay.checked_in.replace(day=1):  # oy o'rtasida kirgan — darhol "muddati o'tgan" bo'lmasin
        due = max(due, stay.checked_in + timedelta(days=settings.INVOICE_DUE_DAY))
    return due


@transaction.atomic
def generate_for_stay(stay: DormStay, *, through: date) -> list[Invoice]:
    """Kirgan oydan `through` oyigacha (chiqqan bo'lsa — chiqqan oygacha) yetishmagan oylar. Idempotent."""
    last = min(through, stay.checked_out) if stay.checked_out else through
    if last < stay.checked_in:
        return []
    existing = set(stay.student.invoices.filter(category=Invoice.Category.DORM)
                   .exclude(status=Invoice.Status.CANCELLED).values_list("month", flat=True))
    full = max(stay.room.monthly_fee, stay.monthly_fee)
    created = []
    for month in invoice_service.month_starts(stay.checked_in, last):
        if month in existing:
            continue
        amount = _month_amount(stay, month)
        if amount <= 0:
            continue
        created.append(Invoice(
            branch=stay.room.branch, student=stay.student, dorm_stay=stay, category=Invoice.Category.DORM,
            month=month, full_amount=full, discount=full - stay.monthly_fee, waived=stay.monthly_fee - amount,
            amount=amount, due_date=_due_date(stay, month)))
    Invoice.objects.bulk_create(created)
    if created:
        logger.info("Yotoqxona grafigi: %s uchun %d oy", stay.student.code, len(created))
    return created


@transaction.atomic
def close_for_stay(stay: DormStay) -> dict:
    """Chiqqandan keyin: chiqqan oy kunlar bo'yicha, keyingi to'lanmagan oylar bekor. Qaytaradi: {"kept": n}."""
    left_month = stay.checked_out.replace(day=1)
    kept = 0
    for inv in stay.invoices.select_for_update().exclude(status=Invoice.Status.CANCELLED):
        if inv.month > left_month:
            if inv.paid == 0:
                inv.status = Invoice.Status.CANCELLED
                inv.save(update_fields=["status", "updated_at"])
            else:
                kept += 1  # oldindan to'langan — o'chirilmaydi, pul qaytarish alohida (o'qishdan chiqarish orqali)
        elif inv.month == left_month:
            new_amount = max(_month_amount(stay, inv.month), inv.paid)
            if new_amount < inv.amount:
                inv.waived += inv.amount - new_amount
                inv.amount = new_amount
                inv.refresh_status()
                inv.save(update_fields=["amount", "waived", "status", "updated_at"])
    return {"kept": kept}


def generate_due_months(today: date) -> int:
    """Cron: hozir yashayotganlar uchun joriy oygacha yetishmagan yotoqxona oylari."""
    total = 0
    for stay in (DormStay.objects.filter(checked_out__isnull=True, student__status__in=["active", "frozen"])
                 .select_related("student", "room__branch")):
        total += len(generate_for_stay(stay, through=today))
    return total
