import re

import pytest
from django.urls import reverse

from apps.accounts.domain.phone import normalize_phone
from apps.accounts.infrastructure.sms import LocmemSMSBackend
from apps.accounts.models import OneTimeCode, Role, User, UserRole
from apps.accounts.session import SESSION_ROLE_KEY
from apps.core.models import Branch

PASSWORD = "test-pass-123"


@pytest.fixture(autouse=True)
def clear_outbox():
    LocmemSMSBackend.outbox.clear()


@pytest.fixture
def branch(db):
    return Branch.objects.create(name="Test filial")


@pytest.fixture
def teacher(branch):
    user = User.objects.create_user("998901112233", PASSWORD, last_name="Aliyev", first_name="Vali")
    UserRole.objects.create(user=user, role=Role.TEACHER, branch=branch)
    return user


def sent_code():
    phone, text = LocmemSMSBackend.outbox[-1]
    return re.search(r"\b(\d{6})\b", text).group(1)


@pytest.mark.parametrize("raw", ["+998 90 111 22 33", "90 111-22-33", "998901112233", "901112233"])
def test_normalize_phone(raw):
    assert normalize_phone(raw) == "998901112233"


def test_login_page_renders(client, branch):
    assert client.get(reverse("accounts:login")).status_code == 200
    assert client.get(reverse("accounts:login") + "?method=password").status_code == 200


def test_password_login(client, teacher):
    resp = client.post(reverse("accounts:login") + "?method=password",
                       {"method": "password", "phone": "90 111 22 33", "password": PASSWORD})
    assert resp.status_code == 302
    assert client.session[SESSION_ROLE_KEY] == teacher.roles.get().pk
    assert client.get(reverse("core:home")).status_code == 200


def test_wrong_password(client, teacher):
    resp = client.post(reverse("accounts:login"), {"method": "password", "phone": "901112233", "password": "x"})
    assert resp.status_code == 200
    assert "noto&#x27;g&#x27;ri" in resp.content.decode()


def test_user_without_role_cannot_login(client, branch):
    User.objects.create_user("998905556677", PASSWORD, last_name="A", first_name="B")
    resp = client.post(reverse("accounts:login"), {"method": "password", "phone": "905556677", "password": PASSWORD})
    assert resp.status_code == 200
    assert "_auth_user_id" not in client.session


def test_otp_login_flow(client, teacher):
    resp = client.post(reverse("accounts:login"), {"method": "code", "phone": "90 111 22 33", "remember": "on"})
    assert resp.url == reverse("accounts:verify")
    code = sent_code()

    otp = OneTimeCode.objects.get()
    assert code not in otp.code_hash  # kod ochiq saqlanmaydi

    resp = client.post(reverse("accounts:verify"), {"code": code})
    assert resp.url == reverse("core:home")
    assert int(client.session["_auth_user_id"]) == teacher.pk


def test_otp_unknown_phone_does_not_send_but_same_response(client, branch):
    resp = client.post(reverse("accounts:login"), {"method": "code", "phone": "909999999"})
    assert resp.url == reverse("accounts:verify")
    assert LocmemSMSBackend.outbox == []


def test_otp_wrong_code_and_attempt_limit(client, teacher, settings):
    client.post(reverse("accounts:login"), {"method": "code", "phone": "901112233"})
    for _ in range(settings.OTP_MAX_ATTEMPTS):
        resp = client.post(reverse("accounts:verify"), {"code": "000000" if sent_code() != "000000" else "111111"})
        assert resp.status_code == 200
    # Limitdan keyin hatto to'g'ri kod ham qabul qilinmaydi
    resp = client.post(reverse("accounts:verify"), {"code": sent_code()})
    assert resp.status_code == 200
    assert "_auth_user_id" not in client.session


def test_otp_resend_is_throttled(client, teacher):
    client.post(reverse("accounts:login"), {"method": "code", "phone": "901112233"})
    client.post(reverse("accounts:resend"))
    assert len(LocmemSMSBackend.outbox) == 1


def test_role_switch(client, teacher, branch):
    reception = UserRole.objects.create(user=teacher, role=Role.RECEPTION, branch=branch)
    client.force_login(teacher)
    client.post(reverse("accounts:switch_role", args=[reception.pk]))
    assert client.session[SESSION_ROLE_KEY] == reception.pk
    assert 'data-role="reception"' in client.get(reverse("core:home")).content.decode()


def test_cannot_switch_to_foreign_role(client, teacher, branch):
    other = User.objects.create_user("998907778899", PASSWORD, last_name="C", first_name="D")
    foreign = UserRole.objects.create(user=other, role=Role.RECEPTION, branch=branch)
    client.force_login(teacher)
    assert client.post(reverse("accounts:switch_role", args=[foreign.pk])).status_code == 404


def test_section_placeholder_respects_role(client, teacher):
    client.force_login(teacher)
    assert client.get(reverse("core:section", args=["my-schedule"])).status_code == 200
    assert client.get(reverse("core:section", args=["cashbox"])).status_code == 404  # reception bo'limi
