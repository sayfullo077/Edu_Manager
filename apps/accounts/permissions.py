"""Rol asosidagi kirish nazorati (interface qatlami)."""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import Role

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def role_required(*roles: Role):
    """Faqat faol roli ro'yxatda bo'lgan foydalanuvchi kira oladi (aks holda 403).

    Ma'lumotlar faol rolning filiali bilan cheklanadi: `request.branch`.
    """

    def decorator(view):
        @login_required
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            active = request.active_role
            if not (active and active.role in roles):
                raise PermissionDenied
            # Direktor — nazorat roli: faqat ko'radi. O'zgartirish faqat @director_can_write belgilangan
            # view'larda (rahbar qarorlari: byudjet limitlari, oylik sozlamalari, xodimlar kirishi).
            if (active.role == Role.DIRECTOR and request.method not in SAFE_METHODS
                    and not getattr(view, "director_can_write", False)):
                raise PermissionDenied
            request.branch = active.branch
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def director_can_write(view):
    """Direktorga shu view'da o'zgartirish (POST) ruxsat — rahbar qarori. `role_required` dan PASTDA qo'yiladi."""
    view.director_can_write = True
    return view
