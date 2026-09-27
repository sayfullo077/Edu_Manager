"""Autentifikatsiya domenidagi xatolar. Xabarlar foydalanuvchiga ko'rsatishga tayyor (o'zbekcha)."""

from apps.common.ratelimit import RateLimited

__all__ = ["AuthError", "InvalidCredentials", "NoRoleAssigned", "OTPError", "RateLimited"]


class AuthError(Exception):
    """Kirishdagi barcha kutilgan xatolar uchun asosiy klass."""


class InvalidCredentials(AuthError):
    def __init__(self):
        super().__init__("Login yoki parol noto'g'ri.")


class NoRoleAssigned(AuthError):
    def __init__(self):
        super().__init__("Sizga hali rol biriktirilmagan. Administratorga murojaat qiling.")


class OTPError(AuthError):
    pass
