import json
import re

import pytest
from django.urls import reverse

from apps.accounts.infrastructure.sms import LocmemSMSBackend
from apps.accounts.infrastructure.telegram import LocmemTelegramBackend
from apps.accounts.models import Role, TelegramLink, User, UserRole
from apps.accounts.services.telegram_linking import handle_update
from apps.core.models import Branch

CHAT_ID = 555001
TG_USER_ID = 777001


@pytest.fixture(autouse=True)
def clear_outboxes():
    LocmemSMSBackend.outbox.clear()
    LocmemTelegramBackend.outbox.clear()


@pytest.fixture
def teacher(db):
    branch = Branch.objects.create(name="Test filial")
    user = User.objects.create_user("998901112233", "x", last_name="Aliyev", first_name="Vali")
    UserRole.objects.create(user=user, role=Role.TEACHER, branch=branch)
    return user


def contact_update(phone="+998901112233", contact_user_id=TG_USER_ID, from_id=TG_USER_ID):
    return {"update_id": 1, "message": {
        "chat": {"id": CHAT_ID, "type": "private"},
        "from": {"id": from_id, "username": "vali"},
        "contact": {"phone_number": phone, "user_id": contact_user_id},
    }}


def test_start_shows_share_button(db):
    handle_update({"update_id": 1, "message": {
        "chat": {"id": CHAT_ID, "type": "private"}, "from": {"id": TG_USER_ID}, "text": "/start login"}})
    assert LocmemTelegramBackend.outbox[-1][0] == CHAT_ID


def test_contact_links_account(teacher):
    handle_update(contact_update())
    link = TelegramLink.objects.get()
    assert (link.user, link.chat_id, link.username) == (teacher, CHAT_ID, "vali")


def test_foreign_contact_is_rejected(teacher):
    # Birovning kontaktini yuborib, uning akkauntiga kodlarni o'g'irlash mumkin bo'lmasligi kerak.
    handle_update(contact_update(contact_user_id=999999))
    assert not TelegramLink.objects.exists()


def test_unknown_phone_is_not_linked(teacher):
    handle_update(contact_update(phone="998909999999"))
    assert not TelegramLink.objects.exists()


def test_group_chats_are_ignored(teacher):
    update = contact_update()
    update["message"]["chat"]["type"] = "group"
    handle_update(update)
    assert not TelegramLink.objects.exists()
    assert LocmemTelegramBackend.outbox == []


def test_telegram_login_flow(client, teacher):
    TelegramLink.objects.create(user=teacher, chat_id=CHAT_ID)
    resp = client.post(reverse("accounts:login"), {"method": "code", "channel": "telegram", "phone": "901112233"})
    assert resp.url == reverse("accounts:verify")
    assert LocmemSMSBackend.outbox == []

    chat_id, text = LocmemTelegramBackend.outbox[-1]
    assert chat_id == CHAT_ID
    code = re.search(r"<code>(\d{6})</code>", text).group(1)

    resp = client.post(reverse("accounts:verify"), {"code": code})
    assert resp.url == reverse("core:home")
    assert int(client.session["_auth_user_id"]) == teacher.pk


def test_telegram_not_linked_sends_nothing_but_same_response(client, teacher):
    resp = client.post(reverse("accounts:login"), {"method": "code", "channel": "telegram", "phone": "901112233"})
    assert resp.url == reverse("accounts:verify")
    assert LocmemTelegramBackend.outbox == [] and LocmemSMSBackend.outbox == []
    page = client.get(reverse("accounts:verify")).content.decode()
    assert "https://t.me/test_school_bot?start=login" in page


def test_webhook_requires_secret(client, teacher):
    url = reverse("accounts:telegram_webhook", args=["test-secret"])
    body = json.dumps(contact_update())

    assert client.post(url, body, content_type="application/json").status_code == 403
    wrong = reverse("accounts:telegram_webhook", args=["wrong"])
    assert client.post(wrong, body, content_type="application/json",
                       headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"}).status_code == 403

    resp = client.post(url, body, content_type="application/json",
                       headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
    assert resp.status_code == 200
    assert TelegramLink.objects.filter(user=teacher).exists()
