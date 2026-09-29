"""To'lov qabul qilish va storno.

- To'lov eng eski to'lanmagan oydan boshlab taqsimlanadi (FIFO).
- Qarzdan ortiq summa qabul qilinmaydi (keyingi oylar grafigi ham qarzga kiradi — oldindan to'lash mumkin).
- Invoice qatorlari `select_for_update` bilan qulflanadi: ikki xodim bir vaqtda to'lov kiritsa ham summa buzilmaydi.
"""

import logging
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.common.templatetags.ui import money

from ..models import Account, Invoice, Payment, PaymentAllocation, Transaction, Withdrawal
from . import cash, ledger

logger = logging.getLogger(__name__)
security_log = logging.getLogger("security")

METHOD_ACCOUNT = {Payment.Method.CASH: Account.Kind.CASH, Payment.Method.CARD: Account.Kind.TERMINAL,
                  Payment.Method.TRANSFER: Account.Kind.BANK}


def outstanding(student, category=Invoice.Category.TUITION) -> Decimal:
    return (student.invoices.filter(category=category, status__in=[Invoice.Status.PENDING, Invoice.Status.PARTIAL])
            .aggregate(v=Sum(F("amount") - F("paid")))["v"] or Decimal("0"))


def _commission(method: str, amount: Decimal) -> Decimal:
    if method != Payment.Method.CARD:
        return Decimal("0")
    pct = Decimal(str(settings.TERMINAL_COMMISSION_PERCENT))
    return (amount * pct / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


@transaction.atomic
def accept_payment(*, student, amount: Decimal, method: str, by, card_network: str = "", payer_name: str = "",
                   note: str = "", category: str = Invoice.Category.TUITION, paid_at=None) -> Payment:
    amount = Decimal(amount)
    if amount <= 0:
        raise ValidationError({"amount": "Summa musbat bo'lishi kerak."})
    if method == Payment.Method.CARD and not card_network:
        raise ValidationError({"card_network": "Karta turini tanlang."})

    invoices = list(student.invoices.select_for_update()
                    .filter(category=category, status__in=[Invoice.Status.PENDING, Invoice.Status.PARTIAL])
                    .order_by("month"))
    debt = sum((i.remaining for i in invoices), Decimal("0"))
    if debt <= 0:
        raise ValidationError({"amount": "O'quvchining to'lanmagan grafigi yo'q (avval shartnomani imzolating)."})
    if amount > debt:
        raise ValidationError({"amount": f"Summa qarzdan oshib ketdi. Maksimal: {money(debt)} so'm."})

    today = timezone.localdate()
    if paid_at is not None:
        day = timezone.localtime(paid_at).date()
        if day > today:
            raise ValidationError({"paid_on": "To'lov sanasi kelajakda bo'lishi mumkin emas."})
        if (today - day).days > settings.PAYMENT_BACKDATE_DAYS:
            raise ValidationError({"paid_on": f"Eng ko'pi {settings.PAYMENT_BACKDATE_DAYS} kun oldingi sana."})
        if method == Payment.Method.CASH and day != today:
            raise ValidationError({"paid_on": "Naqd to'lov faqat bugungi sana bilan (ochiq kassaga) qabul qilinadi."})
    session = cash.require_open_session(student.branch) if method == Payment.Method.CASH else None
    account = ledger.get_account(student.branch, METHOD_ACCOUNT[method])
    paid_at = paid_at or timezone.now()
    payment = Payment.objects.create(
        branch=student.branch, student=student, category=category, amount=amount, method=method,
        card_network=card_network if method == Payment.Method.CARD else "", account=account, cash_session=session,
        paid_at=paid_at, received_by=by, payer_name=payer_name[:120], note=note[:255])

    left = amount
    for invoice in invoices:
        if left <= 0:
            break
        part = min(left, invoice.remaining)
        PaymentAllocation.objects.create(payment=payment, invoice=invoice, amount=part)
        invoice.paid += part
        invoice.refresh_status()
        invoice.save(update_fields=["paid", "status", "updated_at"])
        left -= part

    ledger.record(account=account, direction=Transaction.Direction.IN, kind=Transaction.Kind.PAYMENT,
                  amount=amount, commission=_commission(method, amount), payment=payment, by=by,
                  occurred_at=paid_at, description=f"{student.short_name} — {payment.number}")
    logger.info("To'lov: %s %s %s (user=%s)", payment.number, student.code, amount, by.pk)
    return payment


@transaction.atomic
def reverse_payment(payment: Payment, *, reason: str, by) -> Payment:
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status == Payment.Status.REVERSED:
        raise ValidationError("To'lov allaqachon storno qilingan.")
    if Withdrawal.objects.filter(student_id=payment.student_id).exists():
        raise ValidationError("O'quvchi o'qishdan chiqqan — hisob-kitob yopilgan, storno qilib bo'lmaydi.")
    if not reason.strip():
        raise ValidationError({"reason": "Storno sababini yozing."})
    if payment.method == Payment.Method.CASH:
        cash.require_open_session(payment.branch)

    for alloc in payment.allocations.select_related("invoice").select_for_update():
        invoice = alloc.invoice
        invoice.paid -= alloc.amount
        invoice.refresh_status()
        invoice.save(update_fields=["paid", "status", "updated_at"])

    original = payment.transactions.get(kind=Transaction.Kind.PAYMENT)
    now = timezone.now()
    ledger.record(account=payment.account, direction=Transaction.Direction.OUT, kind=Transaction.Kind.STORNO,
                  amount=original.amount, commission=original.commission, payment=payment, by=by,
                  occurred_at=now, description=f"Storno {payment.number}: {reason}")
    payment.status, payment.reversed_at, payment.reversed_by = Payment.Status.REVERSED, now, by
    payment.reverse_reason = reason.strip()[:255]
    payment.save(update_fields=["status", "reversed_at", "reversed_by", "reverse_reason", "updated_at"])
    security_log.warning("Storno: %s summa=%s sabab=%r (user=%s)", payment.number, payment.amount, reason, by.pk)
    return payment
