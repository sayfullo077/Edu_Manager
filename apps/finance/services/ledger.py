"""Hisoblar va tranzaksiyalar jurnali. Qoldiq hech qayerda saqlanmaydi — har doim jurnaldan hisoblanadi."""

from decimal import Decimal

from django.db.models import DecimalField, F, Q, Sum
from django.db.models.functions import Coalesce

from ..models import Account, Transaction

ZERO = Decimal("0")
ACCOUNT_NAMES = {Account.Kind.CASH: "Naqd kassa", Account.Kind.BANK: "Bank hisobi",
                 Account.Kind.TERMINAL: "Terminal"}


def get_account(branch, kind: str) -> Account:
    account, _ = Account.objects.get_or_create(branch=branch, kind=kind, defaults={"name": ACCOUNT_NAMES[kind]})
    return account


def _net_sum(qs, direction):
    return qs.aggregate(v=Coalesce(Sum(F("amount") - F("commission"), filter=Q(direction=direction)), ZERO,
                                   output_field=DecimalField()))["v"]


def balance(account: Account, until=None) -> Decimal:
    qs = Transaction.objects.filter(account=account)
    if until is not None:
        qs = qs.filter(occurred_at__lte=until)
    return _net_sum(qs, Transaction.Direction.IN) - _net_sum(qs, Transaction.Direction.OUT)


def record(*, account: Account, direction: str, kind: str, amount: Decimal, by, occurred_at,
           commission: Decimal = ZERO, payment=None, expense=None, withdrawal=None,
           description: str = "") -> Transaction:
    return Transaction.objects.create(
        branch=account.branch, account=account, direction=direction, kind=kind, amount=amount,
        commission=commission, payment=payment, expense=expense, withdrawal=withdrawal, occurred_at=occurred_at,
        created_by=by, description=description[:255])
