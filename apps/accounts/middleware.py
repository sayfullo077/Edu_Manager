from functools import cache

from django.urls import reverse
from django.utils.functional import SimpleLazyObject

from . import superadmin
from .selectors import available_roles
from .session import SESSION_ROLE_KEY

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@cache
def _exit_paths() -> frozenset[str]:
    """Qiyofadan chiqish so'rovlari "amal" sifatida sanalmaydi."""
    return frozenset({reverse("accounts:superadmin_stop"), reverse("accounts:logout")})


class ImpersonationMiddleware:
    """Superadmin "foydalanuvchi sifatida kirish" rejimida request.user ni almashtiradi.

    request.impersonator — haqiqiy superadmin (aks holda None). AuthenticationMiddleware'dan keyin turadi.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.impersonator = None
        if request.user.is_authenticated and superadmin.IMPERSONATE_KEY in request.session:
            target = superadmin.impersonation_target(request)
            if target is not None:
                request.impersonator = request.user
                request.user = target
                if request.method not in SAFE_METHODS and request.path not in _exit_paths():
                    superadmin.record_action(request)
        return self.get_response(request)


def _resolve(request):
    user = request.user
    if not user.is_authenticated:
        return [], None
    if user.is_superuser and not request.impersonator:
        # Superadmin: virtual rollar — istalgan filialdagi istalgan panelni ko'ra oladi.
        roles = superadmin.virtual_roles(user)
        return roles, superadmin.active_virtual_role(request, roles)
    roles = available_roles(user)
    for r in roles:
        r.key = f"{r.role}:{r.branch_id}"  # virtual rollar bilan bir xil identifikator (shablon uchun)
    active_id = request.session.get(SESSION_ROLE_KEY)
    active = next((r for r in roles if r.pk == active_id), roles[0] if roles else None)
    if active and active.pk != active_id:
        request.session[SESSION_ROLE_KEY] = active.pk
    return roles, active


class ActiveRoleMiddleware:
    """request.user_roles va request.active_role (UserRole yoki None).

    Lazy: rollar faqat kerak bo'lganda va so'rov davomida bir marta (1 ta SQL) olinadi —
    static, login sahifasi, webhook kabi so'rovlar bazaga umuman bormaydi.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        state = SimpleLazyObject(lambda: _resolve(request))
        request.user_roles = SimpleLazyObject(lambda: state[0])
        request.active_role = SimpleLazyObject(lambda: state[1])
        return self.get_response(request)
