import logging

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


class BaseSMSBackend:
    def send(self, phone: str, text: str) -> None:
        raise NotImplementedError


class ConsoleSMSBackend(BaseSMSBackend):
    """Development: SMS yuborilmaydi, terminalga chiqariladi."""

    def send(self, phone, text):
        print(f"\n[SMS -> +{phone}] {text}\n", flush=True)


class LocmemSMSBackend(BaseSMSBackend):
    """Testlar uchun: yuborilgan xabarlar `outbox` ro'yxatida saqlanadi."""

    outbox: list[tuple[str, str]] = []

    def send(self, phone, text):
        self.outbox.append((phone, text))


# TODO(4-bosqich): EskizSMSBackend — https://notify.eskiz.uz API


def send_sms(phone: str, text: str) -> None:
    import_string(settings.SMS_BACKEND)().send(phone, text)
