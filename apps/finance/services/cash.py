"""Kassa sessiyasi: ochish (boshlang'ich qoldiq jurnaldan) va yopish (sanalgan naqd bilan solishtirish)."""

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import Account, CashSession, Transaction
from . import ledger

logger = logging.getLogger(__name__)
security_log = logging.getLogger("security")


def current_session(branch) -> CashSession | None:
    return CashSession.objects.filter(branch=branch, closed_at__isnull=True).first()


def require_open_session(branch) -> CashSession:
    session = current_session(branch)
    if session is None:
        raise ValidationError("Kassa sessiyasi ochilmagan. Naqd pul bilan ishlashdan oldin kassani oching.")
    return session


def open_session(branch, *, by) -> CashSession:
    opening = ledger.balance(ledger.get_account(branch, Account.Kind.CASH))
    try:
        with transaction.atomic():
            session = CashSession.objects.create(branch=branch, opened_by=by, opening_balance=opening)
    except IntegrityError as e:
        raise ValidationError("Kassa allaqachon ochiq.") from e
    logger.info("Kassa ochildi: branch=%s qoldiq=%s (user=%s)", branch.pk, opening, by.pk)
    return session


@transaction.atomic
def close_session(session: CashSession, *, counted: Decimal, by, note: str = "") -> CashSession:
    session = CashSession.objects.select_for_update().get(pk=session.pk)
    if session.closed_at:
        raise ValidationError("Kassa allaqachon yopilgan.")
    cash = ledger.get_account(session.branch, Account.Kind.CASH)
    expected = ledger.balance(cash)
    now = timezone.now()
    diff = counted - expected
    if diff:
        # Jurnal haqiqatga moslanadi, tafovut alohida yozuv sifatida qoladi (yashirilmaydi).
        ledger.record(account=cash, direction=Transaction.Direction.IN if diff > 0 else Transaction.Direction.OUT,
                      kind=Transaction.Kind.ADJUSTMENT, amount=abs(diff), by=by, occurred_at=now,
                      description=f"Kassa tafovuti ({'ortiqcha' if diff > 0 else 'kamomad'}). {note}".strip())
        security_log.warning("Kassa tafovuti: branch=%s farq=%s (user=%s)", session.branch_id, diff, by.pk)
    session.expected_cash, session.counted_cash = expected, counted
    session.closed_at, session.closed_by, session.note = now, by, note[:255]
    session.save()
    logger.info("Kassa yopildi: branch=%s kutilgan=%s sanalgan=%s", session.branch_id, expected, counted)
    return session
