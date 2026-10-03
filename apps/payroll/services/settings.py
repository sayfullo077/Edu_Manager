"""Oylik sozlamalarini saqlash."""

from ..models import PayrollSettings

FIELDS = ("first_category_percent", "second_category_percent", "specialist_category_percent",
          "highest_category_percent", "certificate_percent", "language_percent", "homeroom_rate")


def save_settings(obj: PayrollSettings, data: dict) -> PayrollSettings:
    for name in FIELDS:
        setattr(obj, name, data[name])
    obj.full_clean()
    obj.save()
    return obj
