"""Rol asosidagi kirish nazorati (interface qatlami)."""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import Role


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
            request.branch = active.branch
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
