"""Use-case: xodimning Telegram chatini akkauntga bog'lash (botga kelgan xabarlarni qayta ishlash).

Oqim:
  1. Xodim botda /start bosadi → bot "📱 Raqamni ulashish" tugmasini ko'rsatadi.
  2. Xodim tugmani bosadi → Telegram kontaktni yuboradi.
  3. Kontakt shu odamniki bo'lsa (contact.user_id == from.id) va raqam tizimda bo'lsa,
     TelegramLink yaratiladi. Shundan keyin login kodlari shu chatga keladi.
"""

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.html import escape

from .. import selectors
from ..domain.phone import normalize_phone
from ..infrastructure.telegram import get_backend
from ..models import TelegramLink

logger = logging.getLogger(__name__)
security_log = logging.getLogger("security")

SHARE_BUTTON = "📱 Raqamni ulashish"


def _reply(chat_id, text, reply_markup=None):
    get_backend().send_message(chat_id, text, reply_markup or {"remove_keyboard": True})


def handle_update(update: dict, school_name: str = "Maktab") -> None:
    message = update.get("message")
    if not isinstance(message, dict):
        return
    chat = message.get("chat") or {}
    if chat.get("type") != "private" or not isinstance(chat.get("id"), int):
        return  # guruh/kanal xabarlariga javob bermaymiz
    chat_id = chat["id"]
    sender = message.get("from") or {}
    school = escape(school_name)

    contact = message.get("contact")
    if isinstance(contact, dict):
        _handle_contact(chat_id, sender, contact, school)
        return

    if str(message.get("text") or "").startswith("/start"):
        _reply(chat_id,
               f"Assalomu alaykum! Bu <b>{school}</b> platformasining rasmiy boti.\n\n"
               "Tizimga kirish kodlarini shu yerda olish uchun pastdagi tugma orqali "
               "telefon raqamingizni ulashing.",
               {"keyboard": [[{"text": SHARE_BUTTON, "request_contact": True}]],
                "resize_keyboard": True, "one_time_keyboard": True})
        return

    _reply(chat_id, "Kodlar shu chatga avtomatik keladi. Raqamni qayta ulash uchun /start bosing.")


def _handle_contact(chat_id: int, sender: dict, contact: dict, school: str) -> None:
    # Boshqa odamning kontaktini yuborib, uning kodlarini o'g'irlashning oldini olamiz.
    if contact.get("user_id") != sender.get("id"):
        security_log.warning("Telegram: begona kontakt yuborildi chat_id=%s", chat_id)
        _reply(chat_id, "Iltimos, pastdagi tugma orqali <b>o'zingizning</b> raqamingizni ulashing.")
        return

    try:
        phone = normalize_phone(str(contact.get("phone_number", "")))
    except ValidationError:
        phone = None
    user = selectors.active_user_by_phone(phone) if phone else None
    if user is None:
        _reply(chat_id, "Bu raqam tizimda topilmadi. Maktab ma'muriyatiga murojaat qiling.")
        return

    with transaction.atomic():
        # Chat boshqa akkauntga ulangan bo'lsa — yangisiga ko'chiramiz.
        TelegramLink.objects.filter(chat_id=chat_id).exclude(user=user).delete()
        TelegramLink.objects.update_or_create(
            user=user, defaults={"chat_id": chat_id, "username": str(sender.get("username") or "")[:64]})
    logger.info("Telegram ulandi: user=%s", user.pk)
    _reply(chat_id,
           f"✅ Tayyor, {escape(user.first_name)}! Endi {school} platformasiga kirishda "
           "«Telegram» usulini tanlasangiz, kod shu yerga keladi.")
