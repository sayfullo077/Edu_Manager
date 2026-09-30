from django.utils.functional import SimpleLazyObject

from .navigation import build_menu, build_tabbar


def roles(request):
    active = getattr(request, "active_role", None)
    impersonator = getattr(request, "impersonator", None)
    user = getattr(request, "user", None)
    role = active.role if active else None
    navigation = SimpleLazyObject(lambda: build_menu(role, request.path))
    return {
        "impersonator": impersonator,
        "is_superadmin": bool(user and user.is_authenticated and user.is_superuser and not impersonator),
        "user_roles": getattr(request, "user_roles", []),
        "active_role": active,
        # Lazy: menyu faqat shablon uni chizganda quriladi (login sahifasida umuman kerak emas).
        "navigation": navigation,
        "tabbar": SimpleLazyObject(lambda: build_tabbar(role, navigation)),
    }
