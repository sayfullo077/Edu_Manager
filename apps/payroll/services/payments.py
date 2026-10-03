"""O'qituvchiga avans/oylik berish: kassa yoki bankdan chiqim (xarajat «Ish haqi») + to'lov yozuvi."""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.finance.models import ExpenseCategory
from apps.finance.services.expenses import record_expense

from ..models import SalaryPayment

SALARY_CATEGORY = "Ish haqi"


def salary_category() -> ExpenseCategory:
    category, _ = ExpenseCategory.objects.get_or_create(
        name=SALARY_CATEGORY, defaults={"kind": ExpenseCategory.Kind.NORMATIVE, "icon": "wallet"})
    return category


@transaction.atomic
def pay_salary(*, branch, teacher, month: date, kind: str, amount: Decimal, account_kind: str, paid_on: date,
               by, note: str = "") -> SalaryPayment:
    month = month.replace(day=1)
    if teacher.branch_id != branch.pk:
        raise ValidationError("O'qituvchi bu filialda emas.")
    if kind not in SalaryPayment.Kind.values:
        raise ValidationError("To'lov turi noto'g'ri.")
    if month > timezone.localdate().replace(day=1):
        raise ValidationError("Kelgusi oy uchun oylik berilmaydi.")
    label = SalaryPayment.Kind(kind).label
    expense = record_expense(
        branch=branch, category=salary_category(), amount=amount, account_kind=account_kind, spent_at=paid_on,
        description=f"{label} {month:%Y-%m}: {teacher.user.full_name}", by=by)
    return SalaryPayment.objects.create(branch=branch, teacher=teacher, month=month, kind=kind, amount=amount,
                                        paid_on=paid_on, expense=expense, note=note.strip()[:255], created_by=by)
