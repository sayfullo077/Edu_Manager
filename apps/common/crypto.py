"""Maydon darajasidagi shifrlash (passport, JSHSHIR kabi shaxsiy ma'lumotlar uchun).

- Shifrlash: Fernet (AES-128-CBC + HMAC-SHA256). MultiFernet — kalitni almashtirish (rotation) mumkin:
  yangi kalit ro'yxat boshiga qo'shiladi, eskilari o'qish uchun qoladi.
- Qidirish: shifrlangan qiymat bo'yicha qidirib bo'lmaydi, shuning uchun alohida "blind index"
  (HMAC-SHA256, alohida kalit bilan) saqlanadi — faqat aniq moslik (exact match) qidiruvi uchun.

Baza sizib chiqsa ham (SQL dump, backup) passport/JSHSHIR ochiq ko'rinmaydi.
"""

import base64
import hashlib
import hmac
from functools import cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings


def _derive(label: str) -> bytes:
    return hashlib.sha256(f"{label}:{settings.SECRET_KEY}".encode()).digest()


@cache
def _fernet() -> MultiFernet:
    keys = settings.FIELD_ENCRYPTION_KEYS or [base64.urlsafe_b64encode(_derive("field-encryption")).decode()]
    return MultiFernet([Fernet(k.encode() if isinstance(k, str) else k) for k in keys])


@cache
def _index_key() -> bytes:
    key = settings.FIELD_INDEX_KEY
    return key.encode() if key else _derive("blind-index")


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise ValueError("Shifrlangan qiymatni ochib bo'lmadi (kalit noto'g'ri?)") from e


def blind_index(value: str) -> str:
    normalized = "".join(value.split()).upper()
    return hmac.new(_index_key(), normalized.encode(), hashlib.sha256).hexdigest()
