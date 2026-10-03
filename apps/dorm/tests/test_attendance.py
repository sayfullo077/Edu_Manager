from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.dorm import selectors
from apps.dorm.models import DormAttendance, DormRoom, DormStay
from apps.dorm.services import attendance
from apps.people.models import Student
from conftest import make_staff


def student(branch, name, gender="M"):
    return Student.objects.create(branch=branch, last_name="Test", first_name=name, birth_date=date(2014, 1, 1),
                                  gender=gender, grade=6, joined_at=date(2026, 9, 2))


@pytest.fixture
def zavuch(branch):
    return make_staff(branch, Role.HEAD_TEACHER, "998900000195")


@pytest.fixture
def head_client(client, zavuch):
    client.force_login(zavuch)
    return client


@pytest.fixture
def dorm(branch, zavuch):
    today = timezone.localdate()
    boys = DormRoom.objects.create(branch=branch, name="1-xona", gender="male", capacity=4)
    girls = DormRoom.objects.create(branch=branch, name="29-xona", gender="female", capacity=4)
    a, b, q = student(branch, "Ali"), student(branch, "Bek"), student(branch, "Qizi", "F")
    stay = {}
    for s, room, start in ((a, boys, today - timedelta(days=30)), (b, boys, today - timedelta(days=3)),
                           (q, girls, today - timedelta(days=30))):
        stay[s.first_name] = DormStay.objects.create(student=s, room=room, checked_in=start, monthly_fee=Decimal("0"),
                                                     created_by=zavuch)
    return {"today": today, "a": a, "b": b, "q": q, "stay": stay}


def test_mark_rules(branch, other_branch, dorm, zavuch):
    today, a, b = dorm["today"], dorm["a"], dorm["b"]
    attendance.mark(branch=branch, student_id=a.pk, day=today, status="B", by=zavuch)
    attendance.mark(branch=branch, student_id=a.pk, day=today, status="Y", by=zavuch)  # qayta belgilash
    assert DormAttendance.objects.get().status == "Y"
    attendance.mark(branch=branch, student_id=a.pk, day=today, status="", by=zavuch)   # tozalash
    assert not DormAttendance.objects.exists()
    with pytest.raises(ValidationError):  # yotoqxonaga kelmasdan oldingi kun
        attendance.mark(branch=branch, student_id=b.pk, day=today - timedelta(days=10), status="B", by=zavuch)
    with pytest.raises(ValidationError):  # kelgusi kun
        attendance.mark(branch=branch, student_id=a.pk, day=today + timedelta(days=1), status="B", by=zavuch)
    with pytest.raises(ValidationError):  # boshqa filial
        attendance.mark(branch=other_branch, student_id=a.pk, day=today, status="B", by=zavuch)
    with pytest.raises(ValidationError):
        attendance.mark(branch=branch, student_id=a.pk, day=today, status="X", by=zavuch)


def test_grid_and_stats(branch, dorm, zavuch):
    today, a, q = dorm["today"], dorm["a"], dorm["q"]
    attendance.mark(branch=branch, student_id=a.pk, day=today, status="B", by=zavuch)
    attendance.mark(branch=branch, student_id=a.pk, day=today - timedelta(days=1), status="S", by=zavuch)
    attendance.mark(branch=branch, student_id=q.pk, day=today, status="Y", by=zavuch)
    f = selectors.AttendanceFilters()
    start, end = selectors.attendance_period(f, today)
    assert (end - start).days == 19 and end == today
    rows = selectors.attendance_students(selectors.attendance_stays(branch, f, start, end))
    days = selectors.attendance_days(start, end, today)
    selectors.fill_attendance_rows(rows, days)
    by_name = {r["student"].first_name: r for r in rows}
    assert by_name["Ali"]["totals"] == {"B": 1, "Y": 0, "K": 0, "S": 1}
    bek_cells = by_name["Bek"]["cells"]
    assert [c["active"] for c in bek_cells].count(True) == 4  # 3 kun oldin kelgan: 4 kun faol
    s = selectors.attendance_today(branch, today)
    assert (s["total"], s["male"], s["female"], s["present"], s["absent"], s["unmarked"]) == (3, 2, 1, 1, 1, 1)


def test_attendance_page_mark_and_export(head_client, dorm):
    resp = head_client.get(reverse("dorm:attendance"))
    assert resp.status_code == 200 and resp.context["total"] == 3
    resp = head_client.get(reverse("dorm:attendance"), {"gender": "F"})
    assert [r["student"].first_name for r in resp.context["page"].object_list] == ["Qizi"]
    today = dorm["today"].isoformat()
    resp = head_client.post(reverse("dorm:attendance_mark"), {"student": dorm["a"].pk, "date": today, "status": "K"})
    assert resp.json() == {"ok": True} and DormAttendance.objects.get().status == "K"
    resp = head_client.post(reverse("dorm:attendance_mark"), {"student": "x", "date": today, "status": "K"})
    assert resp.status_code == 400
    resp = head_client.get(reverse("dorm:attendance_export"))
    assert resp.status_code == 200 and "davomat" in resp["Content-Disposition"]


def test_day_sheet_bulk_save(head_client, dorm):
    url = reverse("dorm:attendance_day")
    resp = head_client.get(url)
    assert resp.status_code == 200 and len(resp.context["sheet"]) == 3
    a, b, q = dorm["a"], dorm["b"], dorm["q"]
    head_client.post(url, {"date": dorm["today"].isoformat(), f"s{a.pk}": "B", f"s{b.pk}": "Y", f"s{q.pk}": ""})
    assert dict(DormAttendance.objects.values_list("student__first_name", "status")) == {"Ali": "B", "Bek": "Y"}
    # kelgusi sana — bugunga tushadi (kelajak belgilanmaydi)
    resp = head_client.get(url, {"date": "2099-01-01"})
    assert resp.context["day"] == dorm["today"]


def test_only_head_teacher(staff_client):
    assert staff_client.get(reverse("dorm:attendance")).status_code in (302, 403)
