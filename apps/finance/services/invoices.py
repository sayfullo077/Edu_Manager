"""To'lov grafigi: imzolangan shartnomadan oyma-oy Invoice yaratish.

Aralash usul (2026-09-28 qarori):
- Imzolanganda faqat joriy oygacha yaratiladi (`generate_for_contract(..., through=bugun)`).
- Har oy boshida `manage.py generate_monthly_invoices` (cron, kuniga 1 marta — idempotent) yangi oyni qo'shadi.
- Oldindan to'lash uchun Reception "Grafik" oynasidan keyingi oylarni qo'lda yaratadi (`extend_schedule`).
  Kelajak oylar yaratilmaganda tarif o'zgarsa, ular yangi tarif bilan yaratiladi.

Oy o'rtasida kelgan o'quvchi (oyning INVOICE_PRORATION_GRACE_DAYS-kunidan keyin) birinchi oy uchun
qolgan kunlarga proporsional to'laydi, INVOICE_ROUNDING ga pastga yaxlitlanadi.
Namuna (maktab Excel'i): 1 750 000 × 16/30 = 933 333 → 933 000.
"""

import calendar
import logging
from datetime import date, timedelta
from decimal import ROUND_FLOOR, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import Invoice

logger = logging.getLogger(__name__)


def month_starts(start: date, end: date) -> list[date]:
    months, cur = [], start.replace(day=1)
    while cur <= end:
        months.append(cur)
        cur = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
    return months


def first_month_amount(monthly_fee: Decimal, start: date) -> Decimal:
    if start.day <= settings.INVOICE_PRORATION_GRACE_DAYS:
        return monthly_fee
    days_in_month = calendar.monthrange(start.year, start.month)[1]
    remaining_days = days_in_month - start.day + 1
    raw = Decimal(monthly_fee) * remaining_days / days_in_month
    step = Decimal(settings.INVOICE_ROUNDING)
    return (raw / step).to_integral_value(rounding=ROUND_FLOOR) * step


def due_date_for(month: date, due_day: int | None = None) -> date:
    last_day = calendar.monthrange(month.year, month.month)[1]
    return month.replace(day=min(due_day or settings.INVOICE_DUE_DAY, last_day))


def first_due_date(contract, month: date, due_day: int | None = None) -> date:
    """Muddat. Oy o'rtasida (muddatdan keyin) kelgan o'quvchining birinchi oyi darhol "muddati o'tgan"
    bo'lib qolmasin: kelgan kunidan INVOICE_DUE_DAY kun muhlat."""
    due = due_date_for(month, due_day)
    if month == contract.start_date.replace(day=1):
        due = max(due, contract.start_date + timedelta(days=settings.INVOICE_DUE_DAY))
    return due


def _existing_months(contract) -> set[date]:
    return set(contract.student.invoices.filter(category=Invoice.Category.TUITION)
               .exclude(status=Invoice.Status.CANCELLED).values_list("month", flat=True))


def _build(contract, months: list[date], due_day: int | None = None) -> list[Invoice]:
    first = contract.start_date.replace(day=1)
    created = []
    for month in months:
        amount = first_month_amount(contract.monthly_fee, contract.start_date) if month == first \
            else contract.monthly_fee
        created.append(Invoice(
            branch=contract.branch, student=contract.student, contract=contract,
            category=Invoice.Category.TUITION, month=month, full_amount=contract.full_tariff,
            discount=contract.full_tariff - contract.monthly_fee, waived=contract.monthly_fee - amount,
            amount=amount, due_date=first_due_date(contract, month, due_day)))
    return Invoice.objects.bulk_create(created)


@transaction.atomic
def generate_for_contract(contract, *, through: date | None = None) -> list[Invoice]:
    """Shartnoma boshidan `through` oyigacha (None — shartnoma oxirigacha) yetishmagan oylarni yaratadi.

    Idempotent: mavjud (bekor qilinmagan) oylar qayta yaratilmaydi.
    """
    last = contract.end_date if through is None else min(contract.end_date, through)
    existing = _existing_months(contract)
    created = _build(contract, [m for m in month_starts(contract.start_date, last) if m not in existing])
    if created:
        logger.info("To'lov grafigi: %s uchun %d oy yaratildi", contract.number, len(created))
    return created


@transaction.atomic
def extend_schedule(contract, *, start_month: date, months: int, due_day: int | None = None, by) -> list[Invoice]:
    """"Grafik" oynasi: `start_month` dan boshlab `months` ta oyni oldindan yaratadi (oldindan to'lov uchun).

    Qoidalar: shartnoma imzolangan bo'lishi, oylar shartnoma muddati ichida bo'lishi va grafikda bo'shliq
    qolmasligi kerak (oldingi oy yaratilmagan bo'lsa — avval o'sha). Mavjud oylar o'tkazib yuboriladi.
    """
    if contract.status != contract.Status.SIGNED:
        raise ValidationError("Grafik faqat imzolangan shartnoma uchun yaratiladi.")
    if not 1 <= months <= 12:
        raise ValidationError({"months": "1 dan 12 oygacha."})
    if due_day is not None and not 1 <= due_day <= 28:
        raise ValidationError({"due_date": "Muddat kuni 1–28 oralig'ida bo'lsin."})
    start_month, first, last = start_month.replace(day=1), contract.start_date.replace(day=1), contract.end_date
    wanted = month_starts(start_month, date(start_month.year + (start_month.month + months - 2) // 12,
                                            (start_month.month + months - 2) % 12 + 1, 1))
    if start_month < first or wanted[-1] > last:
        raise ValidationError({"start_month": f"Oylar shartnoma muddatida bo'lsin: "
                                              f"{first:%Y-%m} — {last:%Y-%m}."})
    existing = _existing_months(contract)
    gap = next((m for m in month_starts(contract.start_date, start_month) if m < start_month and m not in existing),
               None)
    if gap:
        raise ValidationError({"start_month": f"Grafikda bo'shliq qoladi — avval {gap:%Y-%m} oyini yarating."})
    created = _build(contract, [m for m in wanted if m not in existing], due_day)
    if not created:
        raise ValidationError({"start_month": "Bu oylar grafikda allaqachon bor."})
    logger.info("Grafik qo'lda: %s %d oy (%s dan) (user=%s)", contract.number, len(created), start_month, by.pk)
    return created


def generate_due_months(today: date) -> int:
    """Cron: barcha imzolangan, amaldagi shartnomalar uchun joriy oygacha yetishmagan oylarni yaratadi."""
    from apps.contracts.models import Contract  # contracts → finance importi aylanib qolmasin

    total = 0
    for contract in (Contract.objects.filter(status=Contract.Status.SIGNED, start_date__lte=today,
                                             student__status__in=["active", "frozen"])
                     .select_related("student", "branch")):
        total += len(generate_for_contract(contract, through=today))
    return total


@transaction.atomic
def cancel_unpaid_for_contract(contract, *, from_month: date) -> int:
    """Shartnoma bekor qilinganda: from_month dan boshlab umuman to'lanmagan oylar bekor qilinadi.
    Qisman to'langanlari qoladi (qarz sifatida) — pulni qaytarish alohida (storno) qaror."""
    return (contract.invoices.filter(month__gte=from_month.replace(day=1), status=Invoice.Status.PENDING)
            .update(status=Invoice.Status.CANCELLED))
