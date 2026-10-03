from decimal import Decimal

import pytest
from django.urls import reverse

from apps.academics.models import Group, GroupSubject, Subject
from apps.accounts.models import Role, User
from apps.people.models import Teacher
from conftest import make_staff


@pytest.fixture
def head_client(client, branch):
    client.force_login(make_staff(branch, Role.HEAD_TEACHER, "998900000180"))
    return client


def make_teacher(branch, phone, last, **kw):
    user = User.objects.create_user(phone, "Str0ng-pass-123", last_name=last, first_name="Test")
    return Teacher.objects.create(user=user, branch=branch, **kw)


@pytest.fixture
def staff(branch):
    math = Subject.objects.create(name="Matematika")
    a = make_teacher(branch, "998901234561", "Aliyev", gender="M", category=Teacher.Category.HIGHEST)
    a.subjects.add(math)
    b = make_teacher(branch, "998907654322", "Boboyeva", gender="F", kind=Teacher.Kind.COORDINATOR,
                     status=Teacher.Status.VACATION)
    c = make_teacher(branch, "998905550003", "Valiyev", status=Teacher.Status.DISMISSED)
    return {"a": a, "b": b, "c": c, "math": math}


def test_teacher_list_stats_and_filters(head_client, staff):
    url = reverse("people:teacher_list")
    resp = head_client.get(url)
    assert resp.context["stats"] == {"total": 3, "active": 1, "vacation": 1, "dismissed": 1}
    assert [f["label"] for f in resp.context["filter_menu"]] == ["Turi", "Status", "Fan", "Jinsi", "Toifa"]

    def names(**params):
        return [t.user.last_name for t in head_client.get(url, params).context["page"].object_list]
    assert names(kind="coordinator") == ["Boboyeva"]
    assert names(status="dismissed") == ["Valiyev"]
    assert names(subject=staff["math"].pk) == ["Aliyev"]
    assert names(gender="F") == ["Boboyeva"]
    assert names(category="highest") == ["Aliyev"]
    assert names(q="765 43") == []  # raqam qismlari alohida so'z — har biri mos kelishi kerak
    assert names(q="7654322") == ["Boboyeva"] and names(q="TCH") == ["Aliyev", "Boboyeva", "Valiyev"]


def test_status_change_blocked_while_teaching(head_client, staff, branch, year, school_class):
    a = staff["a"]
    g = Group.objects.create(branch=branch, academic_year=year, school_class=school_class, code="MAT-4A")
    GroupSubject.objects.create(group=g, subject=staff["math"], teacher=a)
    url = reverse("people:teacher_set_status", args=[a.pk])
    head_client.post(url, {"status": "dismissed"})
    a.refresh_from_db()
    assert a.status == "active"  # guruhi bor — bo'shatib bo'lmaydi
    head_client.post(url, {"status": "vacation"})  # ta'til — mumkin (darslar egasiz qolmaydi)
    a.refresh_from_db()
    assert a.status == "vacation"
    g.is_active = False
    g.save()
    head_client.post(url, {"status": "dismissed"})
    a.refresh_from_db()
    assert a.status == "dismissed"


def test_teacher_detail(head_client, staff):
    t = staff["a"]
    t.passport, t.pinfl, t.card_number = "AB1234567", "31000000000001", "8600123412345678"
    t.save()
    url = reverse("people:teacher_detail", args=[t.pk])
    resp = head_client.get(url)
    html = resp.content.decode()
    assert resp.status_code == 200 and resp.context["tab"] == "info"
    assert "Oliy toifa" in html and "Shaxsiy ma'lumotlar" in html and "Ish ma'lumotlari" in html
    # Shaxsiy raqamlar niqoblangan — to'liq qiymat sahifada yo'q
    assert "AB •••4567" in html and "1234567" not in html
    assert "8600123412345678" not in html and "••••••••••••5678" in html
    assert "31000000000001" not in html


@pytest.mark.parametrize("tab", ["finance", "lessons", "subjects", "certificates"])
def test_teacher_detail_tabs(head_client, staff, tab):
    resp = head_client.get(reverse("people:teacher_detail", args=[staff["a"].pk]), {"tab": tab})
    assert resp.status_code == 200 and resp.context["tab"] == tab
    if tab in ("finance", "lessons"):
        assert resp.context["week"]["total"] == 0 and len(resp.context["week_days"]) == 6


def test_teacher_detail_unknown_tab_falls_back(head_client, staff):
    resp = head_client.get(reverse("people:teacher_detail", args=[staff["a"].pk]), {"tab": "x"})
    assert resp.context["tab"] == "info"


def test_teacher_list_only_head_teacher(staff_client):
    assert staff_client.get(reverse("people:teacher_list")).status_code in (302, 403)


BASE = {
    "kind": "teacher", "status": "active", "category": "second", "last_name": "Yangiyev", "first_name": "Ustoz",
    "middle_name": "Test o'g'li", "birth_date": "1995-03-10", "gender": "M", "phone": "90 777 66 55",
    "passport_series": "ab", "passport_number": "1234567", "pinfl": "3100 0000 0000 01", "education": "higher",
    "specialty": "Matematika o'qituvchisi", "experience_years": "4", "hired_at": "2026-09-02",
    "teaching_languages": ["uz", "ru"], "fixed_salary": "0",
    "cert-TOTAL_FORMS": "1", "cert-INITIAL_FORMS": "0", "cert-MIN_NUM_FORMS": "0", "cert-MAX_NUM_FORMS": "1000",
}


def test_create_teacher_with_user_role_and_certificate(head_client, staff, branch):
    from apps.accounts.models import UserRole
    data = {**BASE, "subjects": [staff["math"].pk], "cert-0-kind": "national", "cert-0-subject": staff["math"].pk,
            "cert-0-number": "A+", "cert-0-issued_on": "2026-05-06", "cert-0-expires_on": "2029-05-05",
            "cert-0-score": "75.64"}
    resp = head_client.post(reverse("people:teacher_create"), data)
    t = Teacher.objects.get(user__phone="998907776655")
    assert resp.url == reverse("people:teacher_detail", args=[t.pk])
    assert t.passport == "AB1234567" and t.teaching_languages == ["uz", "ru"] and t.category == "second"
    assert list(t.subjects.all()) == [staff["math"]] and t.certificates.get().score == Decimal("75.64")
    assert UserRole.objects.filter(user=t.user, role=Role.TEACHER, branch=branch).exists()
    assert t.user.has_usable_password() and not t.user.check_password("998907776655")  # parol telefon emas
    msg = str(list(head_client.get(resp.url).context["messages"])[0])
    assert "vaqtinchalik parol" in msg


def test_create_teacher_phone_rules(head_client, staff):
    url = reverse("people:teacher_create")
    resp = head_client.post(url, {**BASE, "phone": "90 123 45 61"})  # Aliyev — o'qituvchi bor
    assert resp.status_code == 200 and "allaqachon" in str(resp.context["form"].errors)
    User.objects.create_user("998903334455", "Str0ng-pass-123", last_name="Reception", first_name="X")
    head_client.post(url, {**BASE, "phone": "90 333 44 55"})  # o'qituvchi profili yo'q xodim — bog'lanadi
    t = Teacher.objects.get(user__phone="998903334455")
    assert t.user.last_name == "Yangiyev" and User.objects.filter(phone="998903334455").count() == 1


def test_update_teacher_and_delete_certificate(head_client, staff):
    from apps.people.models import Certificate
    a = staff["a"]
    cert = Certificate.objects.create(teacher=a, kind="ielts", subject=staff["math"], issued_on="2026-01-01",
                                      expires_on="2028-01-01")
    data = {**BASE, "phone": "90 123 45 61", "first_name": "Yangi", "cert-TOTAL_FORMS": "1",
            "cert-INITIAL_FORMS": "1", "cert-0-id": cert.pk, "cert-0-kind": "ielts",
            "cert-0-subject": staff["math"].pk, "cert-0-issued_on": "2026-01-01", "cert-0-expires_on": "2028-01-01",
            "cert-0-DELETE": "on"}
    resp = head_client.post(reverse("people:teacher_update", args=[a.pk]), data)
    assert resp.status_code == 302
    a.refresh_from_db()
    assert a.user.first_name == "Yangi" and not a.certificates.exists()
    page = head_client.get(reverse("people:teacher_update", args=[a.pk]))
    assert page.context["form"].initial["passport_series"] == "AB"
