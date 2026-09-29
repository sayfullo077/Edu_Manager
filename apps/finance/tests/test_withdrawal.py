from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.contracts.models import Contract
from apps.finance.models import Account, Invoice, Payment, Transaction, Withdrawal
from apps.finance.services import cash, invoices, ledger, payments
from apps.finance.services import withdrawal as service
from apps.people.models import Guardian, Student, StudentGuardian

D = Decimal


@pytest.fixture
def today(monkeypatch):
    """Chiqish sanasi kelajakda bo'lmasin — "bugun"ni o'quv yili ichiga qo'yamiz."""
    fixed = date(2026, 11, 20)
    monkeypatch.setattr(timezone, "localdate", lambda *a: fixed)
    return fixed


@pytest.fixture
def student(branch, school_class):
    s = Student.objects.create(branch=branch, last_name="Aliyev", first_name="Vali", birth_date=date(2016, 5, 1),
                               gender="M", grade=4, school_class=school_class, joined_at=date(2026, 9, 15))
    g = Guardian.objects.create(last_name="Aliyev", first_name="Anvar", phone="998901112233")
    StudentGuardian.objects.create(student=s, guardian=g, relation="father", is_primary=True)
    return s


@pytest.fixture
def contract(student, year, reception):
    c = Contract.objects.create(
        branch=student.branch, academic_year=year, student=student, guardian=student.guardians.first(),
        full_tariff=D("1750000"), start_date=date(2026, 9, 15), end_date=date(2027, 6, 30),
        status=Contract.Status.SIGNED, created_by=reception)
    invoices.generate_for_contract(c)  # sen: 933 000, keyin 1 750 000 dan
    return c


def pay(student, amount, by, method=Payment.Method.TRANSFER):
    return payments.accept_payment(student=student, amount=D(amount), method=method, by=by)


def test_mid_month_charge_counts_attended_days(contract, today):
    nov = contract.invoices.get(month=date(2026, 11, 1))
    assert service.month_charge(nov, date(2026, 11, 10)) == D("583000")  # 1 750 000 × 10/30 = 583 333
    sep = contract.invoices.get(month=date(2026, 9, 1))
    assert service.month_charge(sep, date(2026, 9, 17)) == D("175000")  # 15–17 sentabr: 3 kun


def test_overpaid_student_gets_refund(contract, student, reception, today):
    pay(student, "4433000", reception)  # sentabr + oktabr + noyabr to'liq
    plan = service.calculate(student, left_on=date(2026, 11, 10))
    assert (plan.charged, plan.refund, plan.debt) == (D("3266000"), D("1167000"), D("0"))

    record = service.withdraw(student, left_on=date(2026, 11, 10), reason="transfer", refund_method="transfer",
                              expected_refund=plan.refund, by=reception)
    nov = contract.invoices.get(month=date(2026, 11, 1))
    assert (nov.amount, nov.paid, nov.status) == (D("583000"), D("583000"), Invoice.Status.PAID)
    assert not contract.invoices.filter(month__gt=date(2026, 11, 1)).exclude(status="cancelled").exists()
    refund = Transaction.objects.get(kind=Transaction.Kind.REFUND)
    assert refund.amount == D("1167000") and refund.withdrawal == record
    bank = ledger.get_account(student.branch, Account.Kind.BANK)
    assert ledger.balance(bank) == D("3266000")
    student.refresh_from_db()
    contract.refresh_from_db()
    assert student.status == Student.Status.LEFT and student.left_at == date(2026, 11, 10)
    assert contract.status == Contract.Status.CANCELLED and record.number in contract.cancel_reason
    assert record.lines.count() == 10  # har bir oy audit uchun saqlanadi


def test_underpaid_student_keeps_debt(contract, student, reception, today):
    pay(student, "933000", reception)
    record = service.withdraw(student, left_on=date(2026, 10, 20), reason="dropout", by=reception, expected_refund=D(0))
    oct_ = contract.invoices.get(month=date(2026, 10, 1))
    assert oct_.amount == D("1129000") and oct_.status == Invoice.Status.PENDING  # 1 750 000 × 20/31
    assert (record.refund, record.debt) == (D("0"), D("1129000"))
    assert payments.outstanding(student) == D("1129000")  # qarzdorlarda ko'rinadi, keyin to'lanadi
    assert not Transaction.objects.filter(kind=Transaction.Kind.REFUND).exists()


def test_cash_refund_needs_open_session_and_money(contract, student, reception, today):
    session = cash.open_session(student.branch, by=reception)
    pay(student, "2683000", reception, method=Payment.Method.CASH)  # sentabr + oktabr
    with pytest.raises(ValidationError):
        service.withdraw(student, left_on=date(2026, 10, 1), reason="other", by=reception)  # usul tanlanmagan
    record = service.withdraw(student, left_on=date(2026, 10, 1), reason="other", refund_method="cash", by=reception)
    assert record.cash_session == session and record.refund == D("2683000") - D("933000") - D("56000")
    assert ledger.balance(ledger.get_account(student.branch, Account.Kind.CASH)) == D("989000")


def test_stale_preview_and_double_withdrawal_rejected(contract, student, reception, today):
    plan = service.calculate(student, left_on=date(2026, 11, 10))
    pay(student, "933000", reception)  # ko'rib chiqilgandan keyin yangi to'lov
    with pytest.raises(ValidationError):
        service.withdraw(student, left_on=date(2026, 11, 10), reason="other", by=reception,
                         expected_refund=plan.refund + 1)
    service.withdraw(student, left_on=date(2026, 11, 10), reason="other", by=reception, expected_refund=D(0))
    with pytest.raises(ValidationError):
        service.calculate(student, left_on=date(2026, 11, 10))
    with pytest.raises(ValidationError):  # hisob-kitobdan keyin storno yo'q
        payments.reverse_payment(Payment.objects.get(), reason="xato", by=reception)


def test_dates_validated(contract, student, today):
    with pytest.raises(ValidationError):
        service.calculate(student, left_on=date(2026, 12, 1))  # kelajak
    with pytest.raises(ValidationError):
        service.calculate(student, left_on=date(2026, 9, 1))  # qabuldan oldin


# ---------- HTTP: o'chirish → hisob-kitob → arxiv ----------

def test_delete_with_money_redirects_to_settlement(staff_client, contract, student, reception, today):
    pay(student, "933000", reception)
    resp = staff_client.post(reverse("people:student_delete", args=[student.pk]))
    assert resp.url == reverse("finance:student_withdraw", args=[student.pk])
    assert Student.objects.get(pk=student.pk).status == Student.Status.ACTIVE  # hech narsa o'zgarmadi

    page = staff_client.get(resp.url, {"left_on": "2026-10-20"})
    assert page.context["plan"].debt == D("1129000")
    resp = staff_client.post(resp.url, {"left_on": "2026-10-20", "reason": "transfer", "expected_refund": "0"})
    assert resp.status_code == 302 and Withdrawal.objects.filter(student=student).exists()

    staff_client.post(reverse("people:student_delete", args=[student.pk]))
    student.refresh_from_db()
    assert student.status == Student.Status.LEFT  # tarix saqlanadi — o'chirilmaydi


def test_head_teacher_cannot_settle(client, branch, contract, student, today):
    from apps.accounts.models import Role
    from conftest import make_staff
    client.force_login(make_staff(branch, Role.HEAD_TEACHER, "998900000111"))
    assert client.get(reverse("finance:student_withdraw", args=[student.pk])).status_code in (302, 403)


def test_expelled_reason_sets_expelled_status(contract, student, reception, today):
    service.withdraw(student, left_on=date(2026, 10, 5), reason="expelled", by=reception, expected_refund=D(0))
    student.refresh_from_db()
    assert student.status == Student.Status.EXPELLED and student.left_at == date(2026, 10, 5)
