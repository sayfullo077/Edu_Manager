"""Direktor qarorlari: xodimning tizimga kirishini yoqish / o'chirish (rol faolligi)."""

import logging

from django.core.exceptions import ValidationError

from apps.accounts.models import UserRole

from .selectors import STAFF_ROLES

logger = logging.getLogger("security")


def set_role_active(role: UserRole, *, branch, active: bool, by) -> UserRole:
    if role.branch_id != branch.pk:
        raise ValidationError("Bu rol boshqa filialga tegishli.")
    if role.role not in STAFF_ROLES:
        raise ValidationError("Direktor va superadmin rollarini faqat superadmin boshqaradi.")
    if role.user_id == by.pk:
        raise ValidationError("O'z rolingizni o'zgartira olmaysiz.")
    if role.is_active != active:
        role.is_active = active
        role.save(update_fields=["is_active", "updated_at"])
        logger.info("Direktor %s: %s roli %s (user=%s)", by.pk, role.get_role_display(),
                    "yoqildi" if active else "o'chirildi", role.user_id)
    return role
