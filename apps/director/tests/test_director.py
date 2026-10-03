from datetime import date
from decimal import Decimal as D

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import ClassAttendance
from apps.accounts.models import Role, User, UserRole
from apps.finance.models import Invoice
from apps.payroll.selectors import payroll_settings
from apps.people.models import Student, Teacher
from conftest import make_staff


@pytest.fixture
def director(branch):
    return make_staff(branch, Role.DIRECTOR, "998900000301")


@pytest.fixture
def dir_client(client, director):
    client.force_login(director)
    return client


def student(branch, name, school_class=None):
    return Student.objects.create(branch=branch, last_name="Test", first_name=name, birth_date=date(2016, 1, 1),
                                  gender="M", grade=4, joined_at=date(2026, 9, 2), school_class=school_class)


# ---------- Ko'rish huquqi ----------

READ_PAGES = ["core:home", "director:finance_report", "director:attendance_report", "director:staff",
              "people:student_list", "people:guardian_list", "people:teacher_list", "contracts:contract_list",
              "finance:payment_list", "finance:transaction_list", "finance:debtor_list", "finance:invoice_list",
              "finance:cashbox", "finance:bank_account", "academics:class_list", "academics:timetable",
              "payroll:list", "dorm:dashboard", "dorm:room_list", "dorm:attendance"]


@pytest.mark.parametrize("name", READ_PAGES)
def test_director_can_view(dir_client, name):
    assert dir_client.get(reverse(name)).status_code == 200


WRITE_PAGES = ["people:student_create", "people:teacher_create", "contracts:contract_new",
               "academics:class_create", "academics:group_create", "dorm:attendance_day"]


@pytest.mark.parametrize("name", WRITE_PAGES)
def test_director_cannot_open_write_pages(dir_client, name):
    assert dir_client.get(reverse(name)).status_code == 403


def test_director_post_blocked_everywhere_except_decisions(dir_client, branch):
    s = student(branch, "Ali")
    # oddiy amal — taqiq (server himoyasi, tugma yashirilmagan bo'lsa ham)
    assert dir_client.post(reverse("people:student_toggle_flag", args=[s.pk, "in_erp"])).status_code == 403
    assert dir_client.post(reverse("payroll:list")).status_code == 403
    # rahbar qarori — ruxsat
    data = {"first_category_percent": "15", "second_category_percent": "10", "specialist_category_percent": "0",
            "highest_category_percent": "20", "certificate_percent": "30", "language_percent": "15",
            "homeroom_rate": "30000", "next": "/payroll/"}
    assert dir_client.post(reverse("payroll:settings"), data).status_code == 302
    assert payroll_settings(branch).highest_category_percent == D("20")


def test_other_roles_cannot_open_director_pages(staff_client):
    for name in ("director:finance_report", "director:attendance_report", "director:staff"):
        assert staff_client.get(reverse(name)).status_code == 403


def test_director_menu_and_readonly_marker(dir_client):
    html = dir_client.get(reverse("people:student_list")).content.decode()
    assert 'data-role="director"' in html and "data-write" in html  # «Yangi o'quvchi» belgilangan → yashiriladi


# ---------- Bosh sahifa va hisobotlar ----------

def test_dashboard_numbers(dir_client, branch, school_class, monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda *a: date(2026, 10, 3))
    a, b = student(branch, "Ali", school_class), student(branch, "Bek", school_class)
    Invoice.objects.create(branch=branch, student=a, month=date(2026, 9, 1), full_amount=D("1750000"),
                           amount=D("1750000"), paid=D("750000"), due_date=date(2026, 9, 10),
                           status=Invoice.Status.PARTIAL)
    by = make_staff(branch, Role.HEAD_TEACHER, "998900000302")
    ClassAttendance.objects.create(school_class=school_class, student=a, date=date(2026, 10, 3), status="B",
                                   marked_by=by)
    ClassAttendance.objects.create(school_class=school_class, student=b, date=date(2026, 10, 3), status="Y",
                                   marked_by=by)
    ctx = dir_client.get(reverse("core:home")).context
    assert ctx["students"]["active"] == 2
    assert ctx["debt"] == {"total": D("1000000"), "students": 1}
    assert ctx["attendance"]["percent"] == 50 and ctx["attendance"]["absent"] == 1
    assert len(ctx["money_trend"]) == 6


def test_finance_report_and_attendance_report(dir_client, branch, school_class, monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda *a: date(2026, 10, 3))
    resp = dir_client.get(reverse("director:finance_report"), {"month": "2026-09"})
    assert resp.status_code == 200 and resp.context["month"] == date(2026, 9, 1) and len(resp.context["year"]) == 12
    student(branch, "Ali", school_class)
    rep = dir_client.get(reverse("director:attendance_report"), {"date": "2026-10-02"}).context
    assert rep["day"] == date(2026, 10, 2) and rep["rows"][0]["state"] == "none" and len(rep["not_marked"]) == 1


# ---------- Xodimlar: kirishni yoqish / o'chirish ----------

def test_staff_toggle_rules(dir_client, branch, other_branch, director):
    teacher_user = User.objects.create_user("998900000303", "Str0ng-pass-123", last_name="Ustoz", first_name="T")
    role = UserRole.objects.create(user=teacher_user, role=Role.TEACHER, branch=branch)
    Teacher.objects.create(user=teacher_user, branch=branch)
    url = reverse("director:staff_toggle", args=[role.pk])
    dir_client.post(url, {"active": "0"})
    role.refresh_from_db()
    assert not role.is_active  # o'chirildi — endi bu rol bilan kira olmaydi
    dir_client.post(url, {"active": "1"})
    role.refresh_from_db()
    assert role.is_active
    # o'z roli va direktor roli — o'zgarmaydi
    own = UserRole.objects.get(user=director, role=Role.DIRECTOR)
    dir_client.post(reverse("director:staff_toggle", args=[own.pk]), {"active": "0"})
    own.refresh_from_db()
    assert own.is_active
    # boshqa filial roli — 404
    foreign = UserRole.objects.create(user=teacher_user, role=Role.RECEPTION, branch=other_branch)
    assert dir_client.post(reverse("director:staff_toggle", args=[foreign.pk]), {"active": "0"}).status_code == 404
    people = dir_client.get(reverse("director:staff")).context["people"]
    assert {p["user"].phone for p in people} >= {"998900000303", "998900000301"}
