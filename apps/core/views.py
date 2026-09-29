from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.module_loading import import_string

from apps.accounts.navigation import find_item


@login_required
def home(request):
    role = request.active_role.role if request.active_role else None
    if role is None and request.user.is_superuser:
        return redirect("accounts:superadmin")  # superadmin hali panel tanlamagan
    dashboard = settings.ROLE_DASHBOARDS.get(role)
    if dashboard:
        return import_string(dashboard)(request)
    return render(request, "core/home.html")


@login_required
def section(request, slug):
    """Hali qurilmagan bo'limlar uchun vaqtinchalik sahifa."""
    role = request.active_role.role if request.active_role else None
    item = find_item(role, slug)
    if item is None:
        raise Http404
    return render(request, "core/coming_soon.html", {"item": item})
