from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.models import Branch

from . import superadmin
from .models import ImpersonationLog, Role, User

PAGE_SIZE = 20


def superadmin_only(view):
    @login_required
    def wrapper(request, *args, **kwargs):
        superadmin.require_superadmin(request)
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


@superadmin_only
def panel(request):
    q = request.GET.get("q", "").strip()[:100]
    role = request.GET.get("role", "")
    users = (User.objects.filter(is_active=True, is_superuser=False, is_staff=False, roles__is_active=True)
             .prefetch_related("roles__branch").distinct().order_by("last_name", "first_name"))
    if role in Role.values:
        users = users.filter(roles__role=role, roles__is_active=True)
    for term in q.split()[:4]:
        digits = "".join(c for c in term if c.isdigit())
        cond = Q(last_name__icontains=term) | Q(first_name__icontains=term)
        if len(digits) >= 3:
            cond |= Q(phone__contains=digits)
        users = users.filter(cond)
    page = Paginator(users, PAGE_SIZE).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "accounts/superadmin_panel.html", {
        "branches": Branch.objects.filter(is_active=True).order_by("name"),
        "roles": Role.choices, "page": page, "q": q, "role": role, "querystring": query.urlencode(),
        "page_range": page.paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1),
        "logs": ImpersonationLog.objects.select_related("target", "branch", "actor")[:10],
    })


@superadmin_only
@require_POST
def view_as_role(request):
    try:
        superadmin.view_as_role(request, role=request.POST.get("role", ""),
                                branch_id=int(request.POST.get("branch") or 0))
    except (ValidationError, ValueError) as e:
        messages.error(request, " ".join(getattr(e, "messages", ["Noto'g'ri so'rov."])))
        return redirect("accounts:superadmin")
    return redirect("core:home")


@superadmin_only
@require_POST
def exit_role_view(request):
    superadmin.exit_role_view(request)
    return redirect("accounts:superadmin")


@superadmin_only
@require_POST
def impersonate(request, user_pk):
    target = get_object_or_404(User, pk=user_pk)
    try:
        superadmin.start_impersonation(request, target)
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
        return redirect("accounts:superadmin")
    messages.info(request, f"Siz endi {target.short_name} sifatida ko'ryapsiz.")
    return redirect("core:home")


@login_required
@require_POST
def stop_impersonation(request):
    """Impersonation paytida request.user — xodim, shuning uchun tekshiruv haqiqiy superadmin bo'yicha."""
    if not request.impersonator:
        raise PermissionDenied
    superadmin.stop_impersonation(request)
    messages.success(request, "Superadmin paneliga qaytdingiz.")
    return redirect("accounts:superadmin")
