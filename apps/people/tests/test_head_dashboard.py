from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.contracts.models import Contract
from apps.finance.services import invoices, payments
from apps.people.models import Guardian, Student, StudentGuardian
from conftest import make_staff


def test_head_teacher_home_is_academic_dashboard(client, branch, school_class):
    client.force_login(make_staff(branch, Role.HEAD_TEACHER, "998900000150"))
    for i, gender in enumerate(["M", "M", "F"]):
        Student.objects.create(branch=branch, last_name="Test", first_name=f"Bola{i}", birth_date=date(2016, 1, 1),
                               gender=gender, grade=4, joined_at=date.today(), school_class=school_class)
    resp = client.get(reverse("core:home"))
    assert resp.templates[0].name == "people/dashboard.html"
    ctx = resp.context
    assert (ctx["stats"]["active"], ctx["stats"]["male"], ctx["stats"]["female"]) == (3, 2, 1)
    assert ctx["stats"]["no_contract"] == 3 and ctx["class_rows"][0]["c"] == school_class
    assert ctx["class_rows"][0]["percent"] == 100 and ctx["avg_class"] == 3
    html = resp.content.decode()
    assert "Kassa" not in html and "kirim" not in html.lower()  # moliya faqat Reception'ga


def test_reception_home_still_finance_dashboard(staff_client):
    assert staff_client.get(reverse("core:home")).templates[0].name == "finance/dashboard.html"


@pytest.fixture
def admitted_student(branch, school_class, year, reception):
    """Imzolangan shartnoma, grafik va bitta to'lovi bor o'quvchi."""
    s = Student.objects.create(branch=branch, last_name="Test", first_name="Tolovchi", birth_date=date(2016, 5, 1),
                               gender="M", grade=4, school_class=school_class, joined_at=date(2026, 9, 2))
    g = Guardian.objects.create(last_name="Test", first_name="Ota", phone="998901112299")
    StudentGuardian.objects.create(student=s, guardian=g, relation="father", is_primary=True)
    c = Contract.objects.create(branch=branch, academic_year=year, student=s, guardian=g,
                                full_tariff=Decimal("1750000"), start_date=date(2026, 9, 2), end_date=date(2027, 6, 30),
                                status=Contract.Status.SIGNED, created_by=reception)
    invoices.generate_for_contract(c)
    p = payments.accept_payment(student=s, amount=Decimal("100000"), method="transfer", by=reception)
    return s, p


def test_head_teacher_sees_payments_read_only(client, branch, admitted_student):
    student, payment = admitted_student
    client.force_login(make_staff(branch, Role.HEAD_TEACHER, "998900000151"))
    html = client.get(reverse("people:student_list")).content.decode()
    assert f"{reverse('people:student_detail', args=[student.pk])}?view=payment" in html  # 💳 tugmasi
    assert '<th class="actions">Amallar</th>' in html
    resp = client.get(reverse("people:student_detail", args=[student.pk]), {"view": "payment"})
    assert resp.context["view"] == "payment" and not resp.context["finance_edit"]
    html = resp.content.decode()
    assert reverse("finance:payment_create", args=[student.pk]) not in html  # to'lov qabul qilish yo'q
    assert reverse("finance:payment_reverse", args=[payment.pk]) not in html  # storno yo'q
    assert reverse("finance:student_withdraw", args=[student.pk]) not in html
    assert "schedule_form" not in resp.context
    assert client.get(reverse("finance:payment_receipt", args=[payment.pk])).status_code == 200  # kvitansiya — ko'rish
    # O'zgartiruvchi amallar yopiq
    assert client.get(reverse("finance:payment_create", args=[student.pk])).status_code == 403
    assert client.post(reverse("finance:payment_reverse", args=[payment.pk]), {"reason": "x"}).status_code == 403
