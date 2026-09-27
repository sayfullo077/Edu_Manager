from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from apps.accounts.navigation import find_item


@login_required
def home(request):
    return render(request, "core/home.html")


@login_required
def section(request, slug):
    """Hali qurilmagan bo'limlar uchun vaqtinchalik sahifa."""
    role = request.active_role.role if request.active_role else None
    item = find_item(role, slug)
    if item is None:
        raise Http404
    return render(request, "core/coming_soon.html", {"item": item, "active_slug": slug})
