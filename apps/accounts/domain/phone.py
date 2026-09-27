import re

from django.core.exceptions import ValidationError

UZ_PHONE_RE = re.compile(r"^998\d{9}$")


def normalize_phone(raw: str) -> str:
    """'+998 90 123-45-67', '90 123 45 67' -> '998901234567'."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 9:
        digits = "998" + digits
    if not UZ_PHONE_RE.match(digits):
        raise ValidationError("Telefon raqam noto'g'ri. Masalan: 90 123 45 67")
    return digits


def format_phone(phone: str) -> str:
    """'998901234567' -> '+998 90 123 45 67'."""
    if not phone or not UZ_PHONE_RE.match(phone):
        return phone or ""
    return f"+998 {phone[3:5]} {phone[5:8]} {phone[8:10]} {phone[10:12]}"
