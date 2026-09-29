"""Xarajatlar va filial byudjeti."""

import logging
from datetime import date, datetime, time
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.common.templatetags.ui import money

from ..models import Account, BudgetLimit, Expense, Transaction
from . import cash, ledger

logger = logging.getLogger(__name__)


@transaction.atomic
def record_expense(*, branch, category, amount: Decimal, account_kind: str, spent_at: date, description: str,
                   by) -> Expense:
    amount = Decimal(amount)
    if amount <= 0:
        raise ValidationError({"amount": "Summa musbat bo'lishi kerak."})
    if spent_at > timezone.localdate():
        raise ValidationError({"spent_at": "Kelajakdagi sana bilan xarajat kiritilmaydi."})
    account = ledger.get_account(branch, account_kind)
    session = None
    if account.kind == Account.Kind.CASH:
        session = cash.require_open_session(branch)
        available = ledger.balance(account)
        if amount > available:
            raise ValidationError({"amount": f"Kassada yetarli naqd yo'q (qoldiq: {money(available)} so'm)."})

    expense = Expense.objects.create(branch=branch, category=category, amount=amount, account=account,
                                     cash_session=session, spent_at=spent_at, description=description[:255],
                                     created_by=by)
    occurred = timezone.now() if spent_at == timezone.localdate() else timezone.make_aware(
        datetime.combine(spent_at, time(12, 0)))
    ledger.record(account=account, direction=Transaction.Direction.OUT, kind=Transaction.Kind.EXPENSE,
                  amount=amount, expense=expense, by=by, occurred_at=occurred,
                  description=f"{category.name}: {description}")
    logger.info("Xarajat: %s %s (user=%s)", category.name, amount, by.pk)
    return expense


def set_limit(*, branch, category, month: date, limit: Decimal, by) -> BudgetLimit:
    if limit < 0:
        raise ValidationError({"limit": "Limit manfiy bo'lmaydi."})
    obj, _ = BudgetLimit.objects.update_or_create(branch=branch, category=category, month=month.replace(day=1),
                                                  defaults={"limit": limit})
    logger.info("Byudjet limiti: %s %s = %s (user=%s)", category.name, month, limit, by.pk)
    return obj
