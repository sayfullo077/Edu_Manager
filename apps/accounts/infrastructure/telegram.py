"""Telegram Bot API gateway (infrastructure qatlami).

Servislar faqat `get_backend().send_message(...)` ni chaqiradi — qaysi backend ishlashini
settings.TELEGRAM_BACKEND belgilaydi (dev: konsol, test: xotira, prod: Bot API).
"""

import json
import urllib.error
import urllib.request

from django.conf import settings
from django.utils.module_loading import import_string

API_ERRORS = (urllib.error.URLError, TimeoutError, ValueError)


class BaseTelegramBackend:
    def send_message(self, chat_id: int, text: str, reply_markup: dict | None = None) -> None:
        raise NotImplementedError


class ConsoleTelegramBackend(BaseTelegramBackend):
    """Development: token bo'lmasa xabar terminalga chiqariladi."""

    def send_message(self, chat_id, text, reply_markup=None):
        print(f"\n[Telegram -> {chat_id}] {text}\n", flush=True)


class LocmemTelegramBackend(BaseTelegramBackend):
    """Testlar uchun."""

    outbox: list[tuple[int, str]] = []

    def send_message(self, chat_id, text, reply_markup=None):
        self.outbox.append((chat_id, text))


class BotAPITelegramBackend(BaseTelegramBackend):
    """Haqiqiy Telegram Bot API (https://core.telegram.org/bots/api)."""

    def __init__(self, token: str | None = None):
        self.token = token or settings.TELEGRAM_BOT_TOKEN

    def call(self, method: str, payload: dict, timeout: int = 10) -> dict:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{self.token}/{method}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — manzil qat'iy https
            return json.loads(resp.read())

    def send_message(self, chat_id, text, reply_markup=None):
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        self.call("sendMessage", payload)


def get_backend() -> BaseTelegramBackend:
    return import_string(settings.TELEGRAM_BACKEND)()


def is_configured() -> bool:
    return bool(settings.TELEGRAM_BOT_USERNAME)


def bot_link(start: str = "login") -> str:
    return f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={start}" if is_configured() else ""
