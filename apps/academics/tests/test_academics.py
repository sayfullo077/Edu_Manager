from datetime import date

import pytest
from django.urls import reverse

from apps.academics import selectors
from apps.academics.models import Group, GroupMembership, SchoolClass, Subject
from apps.accounts.models import Role, User
from apps.people.models import Student, Teacher
from conftest import make_staff


@pytest.fixture
def head_client(client, branch):
    client.force_login(make_staff(branch, Role.HEAD_TEACHER, "998900000160"))
    return client


@pytest.fixture
def teacher(branch):
    user = User.objects.create_user("998900000161", "Str0ng-pass-123", last_name="Ustoz", first_name="Test")
    return Teacher.objects.create(user=user, branch=branch)


@pytest.fixture
def subjects(db):
    return (Subject.objects.create(name="IT (Dasturlash)"), Subject.objects.create(name="Fizika"))


def make_student(branch, name, school_class=None, grade=4):
    return Student.objects.create(branch=branch, last_name="Test", first_name=name, birth_date=date(2016, 1, 1),
                                  gender="M", grade=grade, joined_at=date(2026, 9, 2), school_class=school_class)


def group_data(school_class, subjects, teacher, **kw):
    data = {"school_class": school_class.pk, "code": "it-4a", "kind": "whole_class", "pay_scheme": "per_lesson",
            "rate": "2400", "deduction_percent": "0", "capacity": "30", "is_active": "on",
            "st0-subject": subjects[0].pk, "st0-teacher": teacher.pk}
    data.update(kw)
    return data


def test_only_head_teacher(staff_client):
    assert staff_client.get(reverse("academics:class_list")).status_code in (302, 403)


def test_class_create_rules(head_client, year, teacher):
    url = reverse("academics:class_create")
    base = {"academic_year": year.pk, "name": " 5-A ", "kind": "regular", "language": "uz", "capacity": "25",
            "monthly_tariff": "1750000", "homeroom_teacher": teacher.pk, "is_active": "on"}
    resp = head_client.post(url, {**base, "grade": ""})
    assert resp.status_code == 200 and "darajani" in resp.content.decode()
    resp = head_client.post(url, {**base, "grade": "5"})
    c = SchoolClass.objects.get()
    assert resp.url == reverse("academics:class_detail", args=[c.pk]) and c.name == "5-A"
    assert head_client.post(url, {**base, "grade": "5", "name": "5-A"}).status_code == 200  # nom takrorlanmaydi
    resp = head_client.post(url, {**base, "name": "Aniq1", "kind": "direction", "grade": "7"})
    assert SchoolClass.objects.get(name="Aniq1").grade is None  # yo'nalishda daraja yo'q


def test_capacity_not_below_students(head_client, school_class, branch):
    for i in range(3):
        make_student(branch, f"B{i}", school_class)
    resp = head_client.post(reverse("academics:class_update", args=[school_class.pk]), {
        "academic_year": school_class.academic_year_id, "name": "4-A", "kind": "regular", "grade": "4",
        "language": "uz", "capacity": "2", "monthly_tariff": "1750000", "is_active": "on"})
    assert resp.status_code == 200 and "3 nafar" in resp.content.decode()


def test_list_views_and_stats(head_client, school_class, branch, subjects, teacher):
    make_student(branch, "A", school_class)
    make_student(branch, "Sinfsiz")
    head_client.post(reverse("academics:group_create"), group_data(school_class, subjects, teacher))
    resp = head_client.get(reverse("academics:class_list"))
    c = resp.context["classes"][0]
    assert (c.n_students, c.n_groups) == (1, 1)
    assert resp.context["stats"]["without_class"] == 1 and resp.context["stats"]["no_homeroom"] == 1
    resp = head_client.get(reverse("academics:class_list"), {"view": "groups", "q": "fizika"})
    assert resp.context["count"] == 0  # guruhda faqat IT
    resp = head_client.get(reverse("academics:class_list"), {"view": "groups"})
    assert resp.context["groups"][0].code == "IT-4A" and resp.context["groups"][0].n_class == 1


def test_group_merge_subjects_and_validation(head_client, school_class, subjects, teacher):
    url = reverse("academics:group_create")
    resp = head_client.post(url, group_data(school_class, subjects, teacher, **{"st0-teacher": ""}))
    assert resp.status_code == 200 and Group.objects.count() == 0  # fan o'qituvchisiz
    resp = head_client.post(url, group_data(school_class, subjects, teacher, **{
        "st1-subject": subjects[0].pk, "st1-teacher": teacher.pk}))
    assert resp.status_code == 200 and "ikki marta" in resp.content.decode()
    resp = head_client.post(url, group_data(school_class, subjects, teacher, **{
        "code": "IT+PHYS-Aniq1-01", "kind": "subset", "pay_scheme": "per_student", "rate": "120000",
        "deduction_percent": "15", "st1-subject": subjects[1].pk, "st1-teacher": teacher.pk}))
    g = Group.objects.get()
    assert resp.status_code == 302 and g.subjects.count() == 2 and g.academic_year == school_class.academic_year
    html = head_client.get(reverse("academics:class_list"), {"view": "groups"}).content.decode()
    assert "Birlashma" in html
    resp = head_client.post(url, group_data(school_class, subjects, teacher, **{"deduction_percent": "10"}))
    assert resp.status_code == 200  # darsbayda ushlanma yo'q


def test_subset_members_history_and_capacity(head_client, school_class, branch, subjects, teacher):
    head_client.post(reverse("academics:group_create"), group_data(
        school_class, subjects, teacher, kind="subset", pay_scheme="per_student", rate="120000", capacity="2"))
    g = Group.objects.get()
    a, b, c = (make_student(branch, n, school_class) for n in "ABC")
    add = reverse("academics:group_add_members", args=[g.pk])
    head_client.post(add, {"students": [a.pk, b.pk, c.pk], "on": "2026-09-10"})
    assert g.memberships.count() == 0  # sig'im 2
    head_client.post(add, {"students": [a.pk, b.pk], "on": "2026-09-10"})
    m = g.memberships.get(student=a)
    head_client.post(reverse("academics:group_remove_member", args=[g.pk, m.pk]))
    m.refresh_from_db()
    assert m.left_at is not None  # o'chirilmaydi — tarix
    resp = head_client.get(reverse("academics:group_detail", args=[g.pk]))
    assert resp.context["count"] == 1 and list(resp.context["history"]) == [m]
    assert a in resp.context["members_form"].fields["students"].queryset  # qayta qo'shish mumkin
    head_client.post(add, {"students": [a.pk], "on": "2026-09-20"})
    m.refresh_from_db()
    assert m.left_at is None and m.joined_at == date(2026, 9, 20) and GroupMembership.objects.count() == 2
    assert g in selectors.student_groups(a)


def test_whole_class_members_come_from_class(head_client, school_class, branch, subjects, teacher):
    head_client.post(reverse("academics:group_create"), group_data(school_class, subjects, teacher))
    g = Group.objects.get()
    s = make_student(branch, "A", school_class)
    resp = head_client.get(reverse("academics:group_detail", args=[g.pk]))
    assert list(resp.context["members"]) == [s] and "members_form" not in resp.context
    assert head_client.post(reverse("academics:group_add_members", args=[g.pk]),
                            {"students": [s.pk], "on": "2026-09-10"}).status_code == 302
    assert GroupMembership.objects.count() == 0
    assert selectors.student_groups(s) == [g]  # o'quvchi kartasida ham ko'rinadi


def test_delete_class_and_group(head_client, school_class, branch, year, subjects, teacher):
    empty = SchoolClass.objects.create(branch=branch, academic_year=year, name="11-Z", grade=11)
    head_client.post(reverse("academics:class_delete", args=[empty.pk]))
    assert not SchoolClass.objects.filter(pk=empty.pk).exists()
    head_client.post(reverse("academics:group_create"), group_data(school_class, subjects, teacher))
    g = Group.objects.get()
    head_client.post(reverse("academics:group_delete", args=[g.pk]))
    assert not Group.objects.exists()  # a'zolik tarixi yo'q — o'chirildi
    make_student(branch, "A", school_class)
    head_client.post(reverse("academics:class_delete", args=[school_class.pk]))
    school_class.refresh_from_db()
    assert school_class.is_active is False  # o'quvchisi bor — faolsizlantirildi
    assert not head_client.get(reverse("academics:group_create")).context["form"].fields["school_class"] \
        .queryset.filter(pk=school_class.pk).exists()  # faol bo'lmagan sinfga guruh ochilmaydi
