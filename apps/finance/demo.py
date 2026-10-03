"""Moliya demo ma'lumotlari: hisoblar, xarajat kategoriyalari va limitlar, imzolangan shartnomalar,
to'lov grafiklari, to'lovlar va xarajatlar. Hammasi soxta. Qayta ishga tushirilsa takrorlanmaydi."""

import random
from datetime import datetime, time
from decimal import Decimal

from django.utils import timezone

from apps.contracts.models import Contract
from apps.people.models import Student

from .models import Account, ExpenseCategory, Invoice, Payment
from .services import cash, expenses, invoices, ledger, payments

CATEGORIES = [  # (nomi, turi, ikon, oylik limit)
    ("Kommunal xarajatlar", "fixed", "home", 13_987_627),
    ("Ijaralar", "fixed", "school", 61_409_095),
    ("Oziq-ovqat", "fixed", "receipt", 51_515_407),
    ("Transport xarajatlari", "fixed", "arrows", 30_704_547),
    ("Boshqa xarajatlar", "normative", "briefcase", 13_062_584),
    ("Reklama xarajatlari", "normative", "sparkles", 6_204_727),
    ("To'garaklar", "normative", "users", 8_490_680),
    ("Soliq va bank xarajatlari", "normative", "bank", 10_776_632),
]


def seed(branch, reception_user) -> dict:
    rng = random.Random(7)  # noqa: S311 — faqat demo ma'lumot
    today = timezone.localdate()
    month = today.replace(day=1)
    for kind in Account.Kind.values:
        ledger.get_account(branch, kind)

    for i, (name, kind, icon, limit) in enumerate(CATEGORIES):
        cat, _ = ExpenseCategory.objects.get_or_create(name=name, defaults={"kind": kind, "icon": icon, "order": i})
        expenses.set_limit(branch=branch, category=cat, month=month, limit=Decimal(limit), by=reception_user)

    from apps.core.models import AcademicYear
    year = AcademicYear.current()
    students = list(Student.objects.filter(branch=branch, status=Student.Status.ACTIVE)
                    .select_related("school_class").prefetch_related("guardian_links__guardian", "contracts"))
    for s in students:
        link = next((g for g in s.guardian_links.all() if g.is_primary), None)
        has_contract = any(c.status != Contract.Status.CANCELLED for c in s.contracts.all())
        if has_contract or not (link and s.school_class):
            continue
        discount = Decimal("10") if rng.random() < 0.2 else Decimal("0")
        Contract.objects.create(
            branch=branch, academic_year=year, student=s, guardian=link.guardian, class_name=s.school_class.name,
            full_tariff=s.school_class.monthly_tariff, discount_percent=discount,
            discount_reason="Ikkinchi farzand" if discount else "", start_date=max(s.joined_at, year.start_date),
            end_date=year.end_date, status=Contract.Status.SIGNED, signed_at=timezone.now(),
            signed_phone=link.guardian.phone, created_by=reception_user)
    for contract in Contract.objects.filter(branch=branch, status=Contract.Status.SIGNED):
        invoices.generate_for_contract(contract, through=timezone.localdate())  # idempotent, oyma-oy

    if Payment.objects.filter(branch=branch).exists():
        return {"contracts": Contract.objects.filter(branch=branch).count(),
                "payments": Payment.objects.filter(branch=branch).count()}

    session = cash.current_session(branch) or cash.open_session(branch, by=reception_user)
    for s in students:
        inv = s.invoices.filter(month=month, category=Invoice.Category.TUITION).first()
        if not inv:
            continue
        roll = rng.random()
        amount = inv.amount if roll < 0.78 else (inv.amount / 2).quantize(Decimal("1000")) if roll < 0.9 else 0
        if amount:
            method = rng.choice([Payment.Method.CASH, Payment.Method.CARD, Payment.Method.TRANSFER])
            if method == Payment.Method.CASH:
                paid_at = timezone.now()  # naqd — faqat bugun, ochiq kassaga (to'lov qoidasi)
            else:
                paid_at = min(timezone.now(), timezone.make_aware(datetime.combine(
                    today.replace(day=rng.randint(1, today.day)), time(rng.randint(9, 17), rng.randint(0, 59)))))
            payments.accept_payment(student=s, amount=amount, method=method, by=reception_user, paid_at=paid_at,
                                    card_network="humo" if method == Payment.Method.CARD else "")

    for name, amount in [("Oziq-ovqat", 4_850_000), ("Kommunal xarajatlar", 2_300_000), ("To'garaklar", 900_000)]:
        cat = ExpenseCategory.objects.get(name=name)
        expenses.record_expense(branch=branch, category=cat, amount=Decimal(amount), account_kind="cash",
                                spent_at=today, description="Demo xarajat", by=reception_user)
    cash.close_session(session, counted=ledger.balance(ledger.get_account(branch, "cash")), by=reception_user)
    return {"contracts": Contract.objects.filter(branch=branch).count(),
            "payments": Payment.objects.filter(branch=branch).count()}
