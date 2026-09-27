"""HTTP sessiyasi bilan bog'liq amallar (interface qatlami): login, faol rol."""

from django.contrib.auth import login

from .services.auth import roles_for_login

SESSION_ROLE_KEY = "active_role_id"
REMEMBER_ME_MAX_AGE = 60 * 60 * 24 * 30


def start_session(request, user, branch=None, remember=False) -> None:
    """Rollarni tekshiradi, login qiladi (sessiya kaliti yangilanadi) va birinchi rolni faol qiladi."""
    roles = roles_for_login(user, branch)  # rol bo'lmasa NoRoleAssigned
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session.set_expiry(REMEMBER_ME_MAX_AGE if remember else 0)
    if roles:
        request.session[SESSION_ROLE_KEY] = roles[0].pk
