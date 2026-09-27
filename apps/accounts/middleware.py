from django.utils.functional import SimpleLazyObject

from .selectors import available_roles
from .session import SESSION_ROLE_KEY


def _resolve(request):
    if not request.user.is_authenticated:
        return [], None
    roles = available_roles(request.user)
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
