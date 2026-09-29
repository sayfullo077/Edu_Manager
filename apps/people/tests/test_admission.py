from datetime import date

import pytest
from django.db import connection
from django.urls import reverse

from apps.people.models import Guardian, Student, StudentGuardian
from apps.people.selectors import guardians

STUDENT = {
    "s-last_name": "Aliyev", "s-first_name": "Vali", "s-birth_date": "2016-05-12", "s-gender": "M",
    "s-grade": "4", "s-joined_at": "2026-09-27", "s-status": "active",
}
GUARDIAN = {
    "g-last_name": "Aliyev", "g-first_name": "Anvar", "g-phone": "90 111 22 33",
    "g-pinfl": "31234567890123", "g-passport": "ab1234567", "r-relation": "father",
}


def admit(client, **overrides):
    return client.post(reverse("people:student_create"), {**STUDENT, **GUARDIAN, **overrides})


@pytest.fixture
def admitted(staff_client, school_class):
    resp = admit(staff_client, **{"s-school_class": school_class.pk})
    assert resp.status_code == 302, resp.content.decode()[:500]
    staff_client.get(resp.url)  # flash xabarni "o'qib" qo'yamiz — keyingi sahifalarda ko'rinmasin
    return Student.objects.get()


def test_admission_creates_student_guardian_and_goes_to_contract(staff_client, admitted, branch):
    assert admitted.code == "STD-2026-001"
    assert admitted.branch == branch
    link = StudentGuardian.objects.get()
    assert link.is_primary and link.relation == "father"
    assert link.guardian.passport == "AB1234567"  # katta harfga keltirilgan


def test_admission_redirects_to_contract_step(staff_client, school_class):
    resp = admit(staff_client, **{"s-school_class": school_class.pk})
    assert resp.url == reverse("contracts:contract_create", args=[Student.objects.get().pk])


def test_sibling_reuses_guardian_by_pinfl(staff_client, admitted):
    admit(staff_client, **{"s-first_name": "Madina", "s-gender": "F", "g-first_name": "Boshqa ism"})
    assert Guardian.objects.count() == 1
    assert Guardian.objects.get().child_links.count() == 2
    # Mavjud ma'lumot ustiga yozilmaydi
    assert Guardian.objects.get().first_name == "Anvar"


def test_sibling_reuses_guardian_by_phone_and_surname(staff_client, admitted):
    admit(staff_client, **{"s-first_name": "Madina", "s-gender": "F", "g-pinfl": "", "g-passport": ""})
    assert Guardian.objects.count() == 1


def test_different_person_same_phone_is_new_guardian(staff_client, admitted):
    admit(staff_client, **{"s-last_name": "Karimov", "g-last_name": "Karimov", "g-pinfl": "", "g-passport": ""})
    assert Guardian.objects.count() == 2


def test_admission_is_atomic(staff_client, school_class):
    """Ota-ona ma'lumoti xato bo'lsa, o'quvchi ham saqlanmaydi."""
    resp = admit(staff_client, **{"g-pinfl": "123"})
    assert resp.status_code == 200
    assert Student.objects.count() == 0 and Guardian.objects.count() == 0


def test_grade_must_match_regular_class(staff_client, school_class):
    resp = admit(staff_client, **{"s-school_class": school_class.pk, "s-grade": "7"})
    assert resp.status_code == 200
    assert "mos emas" in resp.content.decode()
    assert Student.objects.count() == 0


def test_personal_ids_encrypted_at_rest_and_searchable(admitted, branch):
    guardian = Guardian.objects.get()
    with connection.cursor() as c:
        c.execute("SELECT pinfl, passport FROM people_guardian WHERE id = %s", [guardian.pk])
        raw_pinfl, raw_passport = c.fetchone()
    assert "31234567890123" not in raw_pinfl and "AB1234567" not in raw_passport
    assert list(guardians(branch, q="3123 4567 8901 23")) == [guardian]
    assert list(guardians(branch, q="ab1234567")) == [guardian]


def test_teacher_cannot_open_reception_pages(client, teacher_user):
    client.force_login(teacher_user)
    for name in ("people:student_list", "people:student_create", "people:guardian_list"):
        assert client.get(reverse(name)).status_code == 403


def test_other_branch_student_is_invisible(client, other_branch, admitted):
    from apps.accounts.models import Role
    from conftest import make_staff
    client.force_login(make_staff(other_branch, Role.RECEPTION, "998900000199"))
    assert client.get(reverse("people:student_detail", args=[admitted.pk])).status_code == 404
    assert admitted.full_name not in client.get(reverse("people:student_list")).content.decode()


def test_student_search_and_default_active_filter(staff_client, admitted):
    Student.objects.create(branch=admitted.branch, last_name="Chiqqanov", first_name="Bola",
                           birth_date=date(2015, 1, 1), gender="M", grade=5, joined_at=date(2026, 9, 2),
                           status=Student.Status.LEFT)
    page = staff_client.get(reverse("people:student_list")).content.decode()
    assert "Aliyev Vali" in page and "Chiqqanov" not in page
    assert "Chiqqanov" in staff_client.get(reverse("people:student_list") + "?status=left").content.decode()
    assert "Aliyev Vali" in staff_client.get(reverse("people:student_list") + "?q=STD-2026").content.decode()


def test_toggle_erp_flag(staff_client, admitted):
    staff_client.post(reverse("people:student_toggle_flag", args=[admitted.pk, "in_erp"]))
    admitted.refresh_from_db()
    assert admitted.in_erp is True
    assert staff_client.post(reverse("people:student_toggle_flag", args=[admitted.pk, "status"])).status_code == 302
    admitted.refresh_from_db()
    assert admitted.status == "active"  # faqat ruxsat etilgan belgilar o'zgaradi


def test_add_second_guardian_and_switch_primary(staff_client, admitted):
    staff_client.post(reverse("people:student_add_guardian", args=[admitted.pk]), {
        "g-last_name": "Aliyeva", "g-first_name": "Zarina", "g-phone": "90 999 88 77", "r-relation": "mother"})
    mother = StudentGuardian.objects.get(relation="mother")
    assert not mother.is_primary
    staff_client.post(reverse("people:student_set_primary_guardian", args=[admitted.pk, mother.pk]))
    assert StudentGuardian.objects.get(is_primary=True) == mother
