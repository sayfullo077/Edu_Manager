"""Kirish use-case'lari. HTTP'dan mustaqil: view faqat shu funksiyalarni chaqiradi.

Himoya qatlamlari:
- SMS bombing / pul sarflash hujumi: IP bo'yicha va telefon bo'yicha kod so'rash limitlari.
- OTP brute force: kod bo'yicha urinishlar (otp.py) + IP bo'yicha tekshirish limiti.
- Parol brute force / credential stuffing: IP bo'yicha va telefon bo'yicha (taqsimlangan hujum) limitlar.
- User enumeration: raqam tizimda bo'lmasa ham javob bir xil.
"""

import logging

from django.contrib.auth import authenticate

from apps.common import ratelimit

from .. import selectors
from ..domain.exceptions import InvalidCredentials, NoRoleAssigned
from ..models import OneTimeCode, User, UserRole
from . import otp

security_log = logging.getLogger("security")


def request_login_code(*, phone: str, channel: str, ip: str, school_name: str) -> None:
    """Kod so'rash. Raqam tizimda yo'q bo'lsa ham xato bermaydi (enumeration bo'lmasin)."""
    ratelimit.enforce("otp_request_ip", ip)
    ratelimit.enforce("otp_request_phone", phone)
    if selectors.active_user_by_phone(phone) is None:
        return
    otp.issue_code(phone, OneTimeCode.Purpose.LOGIN, school_name, channel)


def verify_login_code(*, phone: str, code: str, ip: str) -> User:
    ratelimit.enforce("otp_verify_ip", ip)
    try:
        otp.verify_code(phone, OneTimeCode.Purpose.LOGIN, code)
    except otp.OTPError:
        security_log.info("OTP xato: ip=%s", ip)
        raise
    user = selectors.active_user_by_phone(phone)
    if user is None:  # kod yuborilgandan keyin akkaunt o'chirilgan
        raise InvalidCredentials()
    return user


def password_login(*, request, phone: str, password: str, ip: str) -> User:
    # Faqat muvaffaqiyatsiz urinishlar sanaladi — to'g'ri parol kiritgan odam jazolanmaydi.
    for name, ident in (("password_ip", ip), ("password_phone", phone)):
        result = ratelimit.peek(name, ident)
        if not result.allowed:
            raise ratelimit.RateLimited(result.retry_after)

    user = authenticate(request, phone=phone, password=password)
    if user is None:
        ratelimit.hit("password_ip", ip)
        ratelimit.hit("password_phone", phone)
        security_log.info("Parol xato: ip=%s", ip)
        raise InvalidCredentials()

    ratelimit.reset("password_phone", phone)
    return user


def roles_for_login(user: User, branch=None) -> list[UserRole]:
    roles = selectors.available_roles(user, branch)
    if not roles and not user.is_superuser:
        raise NoRoleAssigned()
    return roles
