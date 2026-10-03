from datetime import date, timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import Role, UserRole
from apps.accounts.permissions import director_can_write, role_required
from apps.common.charts import dual_line_chart
from apps.finance.selectors import MONTHS_UZ_FULL
from apps.payroll.forms import parse_month

from . import selectors, services

DIRECTOR = (Role.DIRECTOR,)


def _month_nav(month: date, today: date) -> dict:
    return {"month": month, "month_label": f"{MONTHS_UZ_FULL[month.month]} {month.year}",
            "prev_month": (month - timedelta(days=1)).replace(day=1),
            "next_month": (month + timedelta(days=32)).replace(day=1), "this_month": today.replace(day=1)}


@role_required(*DIRECTOR)
def dashboard(request):
    """Direktor bosh sahifasi: maktab holati bir qarashda (ta'lim, moliya, oylik, davomat, yotoqxona)."""
    ctx = selectors.dashboard(request.branch, timezone.localdate())
    ctx["trend"] = ctx["student_trend"]
    ctx["trend_chart"] = dual_line_chart(ctx["trend"], "total", "left")
    return render(request, "director/dashboard.html", ctx)


@role_required(*DIRECTOR)
def finance_report(request):
    today = timezone.localdate()
    month = parse_month(request.GET.get("month"), today)
    ctx = selectors.finance_report(request.branch, month)
    ctx.update(_month_nav(month, today))
    return render(request, "director/finance_report.html", ctx)


@role_required(*DIRECTOR)
def attendance_report(request):
    today = timezone.localdate()
    try:
        day = min(date.fromisoformat(request.GET.get("date", "")), today)
    except ValueError:
        day = today
    ctx = selectors.attendance_report(request.branch, day)
    ctx.update(today=today, prev_day=day - timedelta(days=1), next_day=day + timedelta(days=1))
    return render(request, "director/attendance_report.html", ctx)


@role_required(*DIRECTOR)
def staff(request):
    everyone = selectors.staff(request.branch)
    people = everyone
    q = (request.GET.get("q") or "").strip().lower()
    if q:
        people = [p for p in people if q in p["user"].full_name.lower() or q in p["user"].phone]
    return render(request, "director/staff.html", {
        "people": people, "stats": selectors.staff_stats(everyone), "q": q})


@role_required(*DIRECTOR)
@require_POST
@director_can_write
def staff_toggle(request, pk):
    role = get_object_or_404(UserRole.objects.select_related("user"), pk=pk, branch=request.branch)
    active = request.POST.get("active") == "1"
    try:
        services.set_role_active(role, branch=request.branch, active=active, by=request.user)
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    else:
        messages.success(request, f"{role.user.short_name}: «{role.get_role_display()}» kirishi "
                                  f"{'yoqildi' if active else 'o‘chirildi'}.")
    return redirect("director:staff")
