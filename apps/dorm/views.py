from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import Role
from apps.accounts.permissions import role_required
from apps.common import excel
from apps.common.forms import apply_errors, filter_menu

from . import selectors
from .forms import CheckInForm, CheckOutForm, ResidentFilterForm, RoomFilterForm
from .models import DormRoom, DormStay
from .services import stays

DORM_ROLES = (Role.RECEPTION,)
STEP = 20  # "Yana yuklash" har safar shuncha qo'shadi


@role_required(*DORM_ROLES)
def dashboard(request):
    """Yotoqxona — umumiy ko'rinish: bandlik va hozir yashayotgan o'quvchilar."""
    form = ResidentFilterForm(request.GET or None, branch=request.branch)
    qs = selectors.residents(request.branch, form.to_filters())
    try:
        limit = max(STEP, min(int(request.GET.get("limit", STEP)), 1000))
    except ValueError:
        limit = STEP
    total = qs.count()
    query = request.GET.copy()
    query["limit"] = limit + STEP
    return render(request, "dorm/dashboard.html", {
        "form": form, "o": selectors.occupancy(request.branch), "residents": qs[:limit], "total": total,
        "shown": min(limit, total), "more_query": query.urlencode(), "querystring": request.GET.urlencode(),
    })


RESIDENT_EXPORT_HEADERS = ["#", "O'quvchi", "Kodi", "Jinsi", "Sinf", "Filial (o'quvchi)", "Xona", "Xona filiali",
                           "Kirgan sana", "Izoh"]


@role_required(*DORM_ROLES)
def residents_export(request):
    form = ResidentFilterForm(request.GET or None, branch=request.branch)
    qs = selectors.residents(request.branch, form.to_filters())[:10_000]
    rows = ([n, s.student.full_name, s.student.code, s.student.get_gender_display(),
             getattr(s.student.school_class, "name", ""), s.student.branch.name, s.room.name, s.room.branch.name,
             s.checked_in, s.note] for n, s in enumerate(qs, start=1))
    content = excel.build_workbook("Yotoqxona", RESIDENT_EXPORT_HEADERS, rows)
    return excel.xlsx_response(f"yotoqxona-{timezone.localdate():%Y-%m-%d}.xlsx", content)


# ---------- Xonalar ----------

@role_required(*DORM_ROLES)
def room_list(request):
    form = RoomFilterForm(request.GET or None)
    qs = selectors.rooms_list(request.branch, form.to_filters())
    active = form.active_filters()
    q = form.data.get("q", "")
    return render(request, "dorm/room_list.html", {
        "form": form, "rooms": qs, "stats": selectors.rooms_stats(request.branch),
        "filter_menu": filter_menu(form, active), "active_filters": active, "has_filters": bool(active or q),
        "q": q, "querystring": request.GET.urlencode(),
    })


ROOM_EXPORT_HEADERS = ["#", "Xona", "Qavat", "Turi", "Jinsi", "Band", "Sig'im", "Bo'sh", "Oylik to'lov", "Holati"]


@role_required(*DORM_ROLES)
def room_export(request):
    form = RoomFilterForm(request.GET or None)
    rows = ([n, r.name, r.floor, r.get_room_type_display(), r.get_gender_display(), r.occupied, r.capacity,
             max(r.capacity - r.occupied, 0), r.monthly_fee, r.get_status_display()]
            for n, r in enumerate(selectors.rooms_list(request.branch, form.to_filters()), start=1))
    content = excel.build_workbook("Xonalar", ROOM_EXPORT_HEADERS, rows)
    return excel.xlsx_response(f"yotoqxona-xonalar-{timezone.localdate():%Y-%m-%d}.xlsx", content)


@role_required(*DORM_ROLES)
def room_detail(request, pk):
    """Xona: hozir yashayotganlar, joylashtirish (POST) va chiqqanlar tarixi."""
    try:
        room = selectors.room_detail(request.branch, pk)
    except DormRoom.DoesNotExist as e:
        raise Http404 from e
    form = CheckInForm(request.POST or None, room=room, initial={"on": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            stay = stays.check_in(student=d["student"], room=room, on=d["on"], note=d["note"], by=request.user)
        except ValidationError as e:
            apply_errors(form, e)
        else:
            messages.success(request, f"{stay.student.short_name} «{room.name}» ga joylashtirildi.")
            return redirect("dorm:room_detail", pk=room.pk)
    return render(request, "dorm/room_detail.html", {
        "room": room, "form": form, "residents": selectors.room_residents(room),
        "history": selectors.room_history(room), "today": timezone.localdate(),
    })


@role_required(*DORM_ROLES)
@require_POST
def stay_check_out(request, pk):
    stay = get_object_or_404(DormStay.objects.select_related("student", "room"), pk=pk,
                             room__branch=request.branch)
    form = CheckOutForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Chiqish sanasini kiriting.")
    else:
        try:
            stays.check_out(stay, on=form.cleaned_data["on"], by=request.user)
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
        else:
            messages.success(request, f"{stay.student.short_name} yotoqxonadan chiqarildi.")
    return redirect("dorm:room_detail", pk=stay.room_id)
