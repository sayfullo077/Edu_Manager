from .navigation import navigation_for


def roles(request):
    active = getattr(request, "active_role", None)
    return {
        "user_roles": getattr(request, "user_roles", []),
        "active_role": active,
        "navigation": navigation_for(active.role if active else None),
    }
