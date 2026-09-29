"""Superadmin: istalgan rol yoki foydalanuvchi qiyofasida tizimni tekshirish.

Ikki rejim:
- ROLE — superadmin o'z akkauntida qoladi, "virtual" rol oladi (Reception/Zavuch/O'qituvchi + filial).
  Bazada UserRole yaratilmaydi.
- USER — so'rov davomida request.user tanlangan xodimga almashtiriladi (request.impersonator — haqiqiy
  superadmin). Sessiya superadminniki bo'lib qoladi: "Qaytish" darhol ishlaydi, qayta login shart emas.

Xavfsizlik: faqat superadmin; boshqa superadmin/xodim-admin qiyofasiga kirilmaydi; har bir boshlanish,
tugash va impersonation paytidagi har bir o'zgartirish (POST) audit jurnaliga yoziladi.
"""

import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import F
from django.utils import timezone

from apps.core.models import Branch

from .models import ROLE_ORDER, ImpersonationLog, Role, User, UserRole
from .session import SESSION_ROLE_KEY

VIEW_ROLE_KEY = "su_view_role"      # {"role", "branch_id", "log_id"}
IMPERSONATE_KEY = "su_impersonate"  # {"user_id", "log_id"}

security_log = logging.getLogger("security")


def real_user(request):
    return getattr(request, "impersonator", None) or request.user


def is_superadmin(request) -> bool:
    user = real_user(request)
    return bool(user.is_authenticated and user.is_superuser and user.is_active)


def require_superadmin(request) -> None:
    if not is_superadmin(request) or getattr(request, "impersonator", None):
        raise PermissionDenied


# ---------- Virtual rollar (ROLE rejimi) ----------

def virtual_roles(user) -> list[UserRole]:
    """Barcha faol filiallar × barcha rollar. Saqlanmagan UserRole obyektlari (pk yo'q)."""
    roles = []
    for branch in Branch.objects.filter(is_active=True).order_by("name"):
        for code in sorted(Role.values, key=lambda c: ROLE_ORDER.get(c, 99)):
            r = UserRole(user=user, role=code, branch=branch)
            r.key = f"{code}:{branch.pk}"
            roles.append(r)
    return roles


def active_virtual_role(request, roles: list[UserRole]) -> UserRole | None:
    data = request.session.get(VIEW_ROLE_KEY) or {}
    key = f"{data.get('role')}:{data.get('branch_id')}"
    return next((r for r in roles if r.key == key), None)


def _close_log(log_id) -> None:
    if log_id:
        ImpersonationLog.objects.filter(pk=log_id, ended_at__isnull=True).update(ended_at=timezone.now())


def view_as_role(request, *, role: str, branch_id: int) -> None:
    require_superadmin(request)
    if role not in Role.values:
        raise ValidationError("Noma'lum rol.")
    branch = Branch.objects.filter(pk=branch_id, is_active=True).first()
    if branch is None:
        raise ValidationError("Filial topilmadi.")
    _close_log((request.session.get(VIEW_ROLE_KEY) or {}).get("log_id"))
    log = ImpersonationLog.objects.create(actor=request.user, mode=ImpersonationLog.Mode.ROLE, role=role,
                                          branch=branch, ip=getattr(request, "client_ip", None))
    request.session[VIEW_ROLE_KEY] = {"role": role, "branch_id": branch.pk, "log_id": log.pk}
    security_log.info("Superadmin %s rol sifatida: %s (%s)", request.user.pk, role, branch.name)


def exit_role_view(request) -> None:
    data = request.session.pop(VIEW_ROLE_KEY, None) or {}
    _close_log(data.get("log_id"))


# ---------- Foydalanuvchi sifatida kirish (USER rejimi) ----------

def impersonation_target(request) -> User | None:
    """Middleware uchun: sessiyadagi nishonni tekshirib qaytaradi (yaroqsiz bo'lsa — sessiyani tozalaydi)."""
    data = request.session.get(IMPERSONATE_KEY)
    if not data:
        return None
    user = request.user
    target = User.objects.filter(pk=data.get("user_id"), is_active=True, is_superuser=False, is_staff=False).first()
    if not (user.is_authenticated and user.is_superuser and user.is_active) or target is None:
        request.session.pop(IMPERSONATE_KEY, None)
        _close_log(data.get("log_id"))
        return None
    return target


def start_impersonation(request, target: User) -> None:
    require_superadmin(request)
    if target.is_superuser or target.is_staff:
        raise ValidationError("Administrator qiyofasiga kirib bo'lmaydi.")
    if not target.is_active:
        raise ValidationError("Foydalanuvchi faol emas.")
    if not target.roles.filter(is_active=True, branch__is_active=True).exists():
        raise ValidationError("Bu foydalanuvchiga rol biriktirilmagan — ko'radigan paneli yo'q.")
    exit_role_view(request)
    log = ImpersonationLog.objects.create(actor=request.user, mode=ImpersonationLog.Mode.USER, target=target,
                                          ip=getattr(request, "client_ip", None))
    request.session[IMPERSONATE_KEY] = {"user_id": target.pk, "log_id": log.pk}
    request.session.pop(SESSION_ROLE_KEY, None)
    security_log.warning("IMPERSONATION boshlandi: superadmin=%s → user=%s", request.user.pk, target.pk)


def stop_impersonation(request) -> None:
    data = request.session.pop(IMPERSONATE_KEY, None) or {}
    request.session.pop(SESSION_ROLE_KEY, None)
    _close_log(data.get("log_id"))
    actor = real_user(request)
    security_log.warning("IMPERSONATION tugadi: superadmin=%s ← user=%s", actor.pk, data.get("user_id"))


def record_action(request) -> None:
    """Impersonation paytidagi har bir o'zgartiruvchi so'rov haqiqiy aktyor nomi bilan jurnalga yoziladi."""
    data = request.session.get(IMPERSONATE_KEY) or {}
    if data.get("log_id"):
        ImpersonationLog.objects.filter(pk=data["log_id"]).update(actions=F("actions") + 1)
    security_log.warning("IMPERSONATION amal: superadmin=%s user=%s %s %s", request.impersonator.pk,
                         request.user.pk, request.method, request.path)
