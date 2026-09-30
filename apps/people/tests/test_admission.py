from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from django.urls import reverse

from apps.contracts.models import Contract
from apps.people.models import Guardian, Student, StudentGuardian
from apps.people.selectors import guardians

STUDENT = {
    "s-last_name": "Aliyev", "s-first_name": "Vali", "s-middle_name": "Anvar o'g'li", "s-birth_date": "2016-05-12",
    "s-gender": "M", "s-grade": "4", "s-joined_at": "2026-09-27",
}
FATHER = {
    "father-enabled": "1", "father-last_name": "Aliyev", "father-first_name": "Anvar",
    "father-middle_name": "Karim o'g'li",
    "father-phone": "90 111 22 33", "father-pinfl": "31234567890123", "father-passport": "ab1234567",
}
MOTHER = {
    "mother-enabled": "1", "mother-last_name": "Aliyeva", "mother-first_name": "Zarina",
    "mother-middle_name": "Olim qizi",
    "mother-phone": "90 999 88 77", "mother-pinfl": "41234567890123", "mother-passport": "AC7654321",
}
CONTRACT = {"c-full_tariff": "1750000", "c-start_date": "2026-09-27", "c-discount_percent": "0", "a-signer": "father"}


def admit(client, **overrides):
    return client.post(reverse("people:student_create"), {**STUDENT, **FATHER, **CONTRACT, **overrides})


@pytest.fixture
def admitted(staff_client, school_class):
    resp = admit(staff_client, **{"s-school_class": school_class.pk})
    assert resp.status_code == 302, resp.content.decode()[:500]
    staff_client.get(resp.url)  # flash xabarni "o'qib" qo'yamiz — keyingi sahifalarda ko'rinmasin
    return Student.objects.get()


def test_admission_creates_student_guardian_and_contract(staff_client, admitted, branch):
    assert admitted.code == "STD-2026-001" and admitted.branch == branch and admitted.status == "active"
    link = StudentGuardian.objects.get()
    assert link.is_primary and link.relation == "father"
    assert link.guardian.passport == "AB1234567"  # katta harfga keltirilgan
    contract = Contract.objects.get()
    assert contract.student == admitted and contract.guardian == link.guardian and contract.status == "draft"
    assert contract.monthly_fee == Decimal("1750000") and contract.class_name == "4-A"


def test_admission_redirects_to_contract_for_sms(staff_client, school_class):
    resp = admit(staff_client, **{"s-school_class": school_class.pk})
    assert resp.url == reverse("contracts:contract_detail", args=[Contract.objects.get().pk])


def test_father_mother_and_carrier_with_chosen_signer(staff_client, school_class):
    carrier = {"carrier-enabled": "1", "a-carrier_relation": "grandma", "carrier-last_name": "Aliyeva",
               "carrier-first_name": "Buvi", "carrier-middle_name": "Salim qizi", "carrier-phone": "90 555 44 33",
               "carrier-pinfl": "51234567890123", "carrier-passport": "AD1112223"}
    resp = admit(staff_client, **MOTHER, **carrier, **{"s-school_class": school_class.pk, "a-signer": "carrier",
                                                        "c-discount_percent": "10", "c-discount_reason": "Oila"})
    assert resp.status_code == 302
    links = {link.relation: link for link in StudentGuardian.objects.all()}
    assert set(links) == {"father", "mother", "grandma"}
    assert [r for r, link in links.items() if link.is_primary] == ["grandma"]
    contract = Contract.objects.get()
    assert contract.guardian == links["grandma"].guardian and contract.monthly_fee == Decimal("1575000")


def test_disabled_slot_is_ignored_and_one_guardian_required(staff_client, school_class):
    # Ota o'chirilgan (maydonlari to'ldirilgan bo'lsa ham) — faqat Ona saqlanadi
    resp = admit(staff_client, **MOTHER, **{"father-enabled": "", "a-signer": "mother"})
    assert resp.status_code == 302 and StudentGuardian.objects.get().relation == "mother"
    resp = admit(staff_client, **{"s-first_name": "Yolg'iz", "father-enabled": ""})
    assert resp.status_code == 200 and "Kamida bitta vasiy" in resp.content.decode()
    assert Student.objects.count() == 1


def test_signer_must_be_enabled_guardian(staff_client, school_class):
    resp = admit(staff_client, **{"a-signer": "mother"})
    assert resp.status_code == 200 and Student.objects.count() == 0


def test_discount_needs_reason(staff_client, school_class):
    resp = admit(staff_client, **{"c-discount_percent": "20"})
    assert resp.status_code == 200 and "sababini" in resp.content.decode()
    assert Student.objects.count() == 0 and Guardian.objects.count() == 0  # hammasi yoki hech narsa


def test_sibling_reuses_guardian_by_pinfl(staff_client, admitted):
    admit(staff_client, **{"s-first_name": "Madina", "s-gender": "F", "father-first_name": "Boshqa ism"})
    assert Guardian.objects.count() == 1
    assert Guardian.objects.get().child_links.count() == 2
    # Mavjud ma'lumot ustiga yozilmaydi
    assert Guardian.objects.get().first_name == "Anvar"


def test_different_pinfl_same_phone_and_surname_is_new_guardian(staff_client, admitted):
    admit(staff_client, **{"s-first_name": "Madina", "father-first_name": "Akasi", "father-pinfl": "31234567890999",
                           "father-passport": "AB7777777"})
    assert Guardian.objects.count() == 2


def test_different_person_same_phone_is_new_guardian(staff_client, admitted):
    admit(staff_client, **{"s-last_name": "Karimov", "father-last_name": "Karimov",
                           "father-pinfl": "31234567890555", "father-passport": "AB5555555"})
    assert Guardian.objects.count() == 2


def test_admission_is_atomic(staff_client, school_class):
    """Vasiy ma'lumoti xato bo'lsa, o'quvchi ham, shartnoma ham saqlanmaydi."""
    resp = admit(staff_client, **{"father-pinfl": "123"})
    assert resp.status_code == 200
    assert Student.objects.count() == 0 and Guardian.objects.count() == 0 and Contract.objects.count() == 0


def test_new_mahalla_is_remembered_and_offered(staff_client, school_class):
    from apps.people.models import District, Mahalla
    District.objects.get_or_create(region="Farg'ona viloyati", name="Oltiariq tumani")
    admit(staff_client, **{"s-region": "Farg'ona viloyati", "s-district": "Oltiariq tumani",
                           "s-mahalla": "  Yangi   Hayot MFY "})
    assert Mahalla.objects.get().name == "Yangi Hayot MFY"
    data = staff_client.get(reverse("people:address_mahallas"),
                            {"region": "Farg'ona viloyati", "district": "Oltiariq tumani"}).json()
    assert data == {"mahallas": ["Yangi Hayot MFY"]}
    form = staff_client.get(reverse("people:student_create")).context["district_map"]
    assert "Oltiariq tumani" in form["Farg'ona viloyati"]


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


def test_student_list_print_follows_filters(staff_client, admitted, school_class):
    resp = staff_client.get(reverse("people:student_print"), {"school_class": school_class.pk})
    assert resp.status_code == 200 and resp.context["total"] == 1
    assert list(resp.context["groups"]) == ["4-A"] and "4-A" in resp.context["filter_labels"]
    assert staff_client.get(reverse("people:student_print"), {"status": "left"}).context["total"] == 0
    html = staff_client.get(reverse("people:student_list")).content.decode()
    assert reverse("people:student_print") in html and "badge-info" in html  # "Ro'yxat" tugmasi va Jins ustuni
