"""Bir martalik kodlar (OTP): yaratish, yuborish, tekshirish.

Xavfsizlik:
- Kodning o'zi bazada saqlanmaydi — faqat HMAC (SECRET_KEY bilan).
- Taqqoslash constant-time (timing hujumi bo'lmasin).
- Har bir kodga OTP_MAX_ATTEMPTS urinish, OTP_TTL_SECONDS amal muddati.
- Qayta yuborish oralig'i va IP/telefon limitlari `services.auth` da.
"""

import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.html import escape

from .. import selectors
from ..domain.exceptions import OTPError
from ..infrastructure import telegram
from ..infrastructure.sms import send_sms
from ..models import OneTimeCode

logger = logging.getLogger(__name__)

SMS_MESSAGES = {
    OneTimeCode.Purpose.LOGIN: "{school}: tizimga kirish kodi {code}. Kodni hech kimga bermang.",
    OneTimeCode.Purpose.CONTRACT: "{school}: shartnomani tasdiqlash kodi {code}.",
}
TELEGRAM_MESSAGES = {
    OneTimeCode.Purpose.LOGIN: "🔐 <b>{school}</b>\nTizimga kirish kodi: <code>{code}</code>\n\n"
                               "Kod {minutes} daqiqa amal qiladi. Uni hech kimga bermang.",
}


@dataclass(frozen=True)
class IssueResult:
    otp: OneTimeCode
    delivered: bool


def _hash(phone: str, code: str) -> str:
    return salted_hmac("otp", f"{phone}:{code}").hexdigest()


def seconds_until_resend(phone: str, purpose: str) -> int:
    last_created = (OneTimeCode.objects.filter(phone=phone, purpose=purpose)
                    .values_list("created_at", flat=True).first())
    if not last_created:
        return 0
    elapsed = (timezone.now() - last_created).total_seconds()
    return max(0, int(settings.OTP_RESEND_SECONDS - elapsed))


def issue_code(phone: str, purpose: str, school_name: str = "Maktab",
               channel: str = OneTimeCode.Channel.SMS) -> IssueResult | None:
    """Kod yaratib yuboradi. Telegram tanlangan-u, bot ulanmagan bo'lsa None (kod yaratilmaydi)."""
    wait = seconds_until_resend(phone, purpose)
    if wait:
        raise OTPError(f"Yangi kodni {wait} soniyadan keyin so'rashingiz mumkin.")

    chat_id = None
    if channel == OneTimeCode.Channel.TELEGRAM:
        user = selectors.active_user_by_phone(phone)
        chat_id = user and selectors.telegram_chat_id(user)
        if not chat_id:
            return None

    code = "".join(secrets.choice("0123456789") for _ in range(settings.OTP_LENGTH))
    with transaction.atomic():
        # Oldingi ishlatilmagan kodlar bekor qilinadi — bir vaqtda faqat bitta kod amal qiladi.
        OneTimeCode.objects.filter(phone=phone, purpose=purpose, used_at__isnull=True).update(
            expires_at=timezone.now())
        otp = OneTimeCode.objects.create(
            phone=phone, purpose=purpose, channel=channel,
            code_hash=_hash(phone, code),
            expires_at=timezone.now() + timedelta(seconds=settings.OTP_TTL_SECONDS),
        )

    delivered = _deliver(phone, chat_id, purpose, school_name, code)
    return IssueResult(otp=otp, delivered=delivered)


def _deliver(phone, chat_id, purpose, school_name, code) -> bool:
    if chat_id:
        text = TELEGRAM_MESSAGES[purpose].format(
            school=escape(school_name), code=code, minutes=settings.OTP_TTL_SECONDS // 60)
        try:
            telegram.get_backend().send_message(chat_id, text)
        except telegram.API_ERRORS:
            # Masalan, xodim botni bloklagan (403). Sahifa yiqilmasin — kod shunchaki kelmaydi.
            logger.exception("Telegram orqali kod yuborilmadi (chat_id=%s)", chat_id)
            return False
        return True
    send_sms(phone, SMS_MESSAGES[purpose].format(school=school_name, code=code))
    return True


def verify_code(phone: str, purpose: str, code: str) -> None:
    """Kod to'g'ri bo'lsa hech narsa qaytarmaydi, aks holda OTPError."""
    # Diqqat: xato atomic() blokidan TASHQARIDA ko'tariladi — aks holda urinishlar
    # hisoblagichi rollback bo'lib, limit ishlamay qoladi (buni test ushlagan).
    error = None
    with transaction.atomic():
        # select_for_update: bir vaqtdagi parallel so'rovlar urinishlar limitini chetlab o'tolmasin.
        otp = (OneTimeCode.objects.select_for_update()
               .filter(phone=phone, purpose=purpose, used_at__isnull=True).first())
        if otp is None or otp.expires_at < timezone.now():
            error = "Kod muddati tugagan. Yangi kod so'rang."
        elif otp.attempts >= settings.OTP_MAX_ATTEMPTS:
            error = "Urinishlar soni tugadi. Yangi kod so'rang."
        elif not constant_time_compare(otp.code_hash, _hash(phone, code.strip())):
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            left = settings.OTP_MAX_ATTEMPTS - otp.attempts
            error = (f"Kod noto'g'ri. Yana {left} ta urinish qoldi." if left else
                     "Urinishlar soni tugadi. Yangi kod so'rang.")
        else:
            otp.used_at = timezone.now()
            otp.save(update_fields=["used_at"])
    if error:
        raise OTPError(error)


def purge_expired(older_than_days: int = 7) -> int:
    """Eski kodlarni o'chiradi (jadval cheksiz o'smasin). Cron/Celery beat orqali kuniga bir marta."""
    cutoff = timezone.now() - timedelta(days=older_than_days)
    deleted, _ = OneTimeCode.objects.filter(created_at__lt=cutoff).delete()
    return deleted
