from datetime import date, timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import Role
from apps.accounts.permissions import role_required
from apps.common import excel
from apps.common.forms import apply_errors, filter_menu
from apps.finance import selectors as finance_selectors
from apps.finance.views import DEBTOR_EXPORT_HEADERS, debtor_export_rows, debtor_list_context

from . import selectors
from .forms import (
    AttendanceFilterForm,
    CheckInForm,
    CheckOutForm,
    DormDebtorFilterForm,
    DormInvoiceFilterForm,
    ResidentFilterForm,
    RoomFilterForm,
)
from .models import DormAttendance, DormRoom, DormStay
from .services import attendance as attendance_service
from .services import stays

DORM_ROLES = (Role.RECEPTION,)
DORM_VIEW_ROLES = (*DORM_ROLES, Role.DIRECTOR)  # direktor — faqat ko'radi
STEP = 20  # "Yana yuklash" har safar shuncha qo'shadi


@role_required(*DORM_VIEW_ROLES)
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


@role_required(*DORM_VIEW_ROLES)
def residents_export(request):
    form = ResidentFilterForm(request.GET or None, branch=request.branch)
    qs = selectors.residents(request.branch, form.to_filters())[:10_000]
    rows = ([n, s.student.full_name, s.student.code, s.student.get_gender_display(),
             getattr(s.student.school_class, "name", ""), s.student.branch.name, s.room.name, s.room.branch.name,
             s.checked_in, s.note] for n, s in enumerate(qs, start=1))
    content = excel.build_workbook("Yotoqxona", RESIDENT_EXPORT_HEADERS, rows)
    return excel.xlsx_response(f"yotoqxona-{timezone.localdate():%Y-%m-%d}.xlsx", content)


# ---------- Xonalar ----------

@role_required(*DORM_VIEW_ROLES)
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


@role_required(*DORM_VIEW_ROLES)
def room_export(request):
    form = RoomFilterForm(request.GET or None)
    rows = ([n, r.name, r.floor, r.get_room_type_display(), r.get_gender_display(), r.occupied, r.capacity,
             max(r.capacity - r.occupied, 0), r.monthly_fee, r.get_status_display()]
            for n, r in enumerate(selectors.rooms_list(request.branch, form.to_filters()), start=1))
    content = excel.build_workbook("Xonalar", ROOM_EXPORT_HEADERS, rows)
    return excel.xlsx_response(f"yotoqxona-xonalar-{timezone.localdate():%Y-%m-%d}.xlsx", content)


@role_required(*DORM_VIEW_ROLES)
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
            stay = stays.check_in(student=d["student"], room=room, on=d["on"], note=d["note"],
                                  monthly_fee=d["monthly_fee"], by=request.user)
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



# ---------- Yotoqxona to'lov grafiklari ----------

@role_required(*DORM_VIEW_ROLES)
def invoice_list(request):
    form = DormInvoiceFilterForm(request.GET or None, branch=request.branch)
    qs = finance_selectors.invoices_list(request.branch, form.to_filters())
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    active = form.active_filters()
    q = form.data.get("q", "")
    return render(request, "dorm/invoice_list.html", {
        "form": form, "page": page, "querystring": query.urlencode(), "q": q,
        "page_range": page.paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1),
        "stats": finance_selectors.invoices_stats(qs),
        "filter_menu": filter_menu(form, active), "active_filters": active, "has_filters": bool(active or q),
    })


DORM_INVOICE_EXPORT_HEADERS = ["#", "O'quvchi", "Kodi", "Xona", "Oy", "Jami", "Chegirma", "Kechilgan",
                               "To'lanishi kerak", "To'langan", "Qoldiq", "Muddat", "Holati"]


@role_required(*DORM_VIEW_ROLES)
def invoice_export(request):
    form = DormInvoiceFilterForm(request.GET or None, branch=request.branch)
    qs = finance_selectors.invoices_list(request.branch, form.to_filters())[:20_000]
    rows = ([n, i.student.full_name, i.student.code, i.dorm_stay.room.name if i.dorm_stay else "",
             f"{i.month:%Y-%m}", i.full_amount, i.discount, i.waived, i.amount, i.paid, i.remaining, i.due_date,
             i.get_status_display()] for n, i in enumerate(qs, start=1))
    content = excel.build_workbook("Yotoqxona grafiklari", DORM_INVOICE_EXPORT_HEADERS, rows)
    return excel.xlsx_response(f"yotoqxona-grafiklari-{timezone.localdate():%Y-%m-%d}.xlsx", content)


# ---------- Yotoqxona qarzdorlari ----------

@role_required(*DORM_VIEW_ROLES)
def debtor_list(request):
    """Kelgan oylar bo'yicha yotoqxona qarzi bor o'quvchilar. Sahifa va yon panel — Kirim → Qarzdorlar bilan umumiy."""
    form = DormDebtorFilterForm(request.GET or None, branch=request.branch)
    return render(request, "finance/debtor_list.html", {
        **debtor_list_context(request, form), "title": "Yotoqxona qarzdorlari",
        "list_url_name": "dorm:debtor_list", "export_url_name": "dorm:debtor_export"})


@role_required(*DORM_VIEW_ROLES)
def debtor_export(request):
    form = DormDebtorFilterForm(request.GET or None, branch=request.branch)
    qs = finance_selectors.debtors(request.branch, form.to_filters())[:20_000]
    content = excel.build_workbook("Yotoqxona qarzdorlari", DEBTOR_EXPORT_HEADERS, debtor_export_rows(qs))
    return excel.xlsx_response(f"yotoqxona-qarzdorlar-{timezone.localdate():%Y-%m-%d}.xlsx", content)


# ---------- Davomat (Zavuch) ----------

ATTENDANCE_ROLES = (Role.HEAD_TEACHER,)
ATTENDANCE_VIEW_ROLES = (*ATTENDANCE_ROLES, Role.DIRECTOR)
ATTENDANCE_PAGE = 30


def _attendance(request):
    form = AttendanceFilterForm(request.GET or None, branch=request.branch)
    f = form.to_filters()
    today = timezone.localdate()
    start, end = selectors.attendance_period(f, today)
    rows = selectors.attendance_students(selectors.attendance_stays(request.branch, f, start, end))
    days = selectors.attendance_days(start, end, today)
    return form, rows, days, start, end, today


@role_required(*ATTENDANCE_VIEW_ROLES)
def attendance(request):
    """Yotoqxona davomati: o'quvchilar × kunlar to'ri, katakni bosib belgilash."""
    form, rows, days, start, end, today = _attendance(request)
    page = Paginator(rows, ATTENDANCE_PAGE).get_page(request.GET.get("page"))
    selectors.fill_attendance_rows(page.object_list, days)
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "dorm/attendance.html", {
        "form": form, "page": page, "days": days, "start": start, "end": end, "today": today,
        "stats": selectors.attendance_today(request.branch, today), "statuses": DormAttendance.Status.choices,
        "can_mark": request.active_role.role != Role.DIRECTOR,
        "querystring": query.urlencode(), "total": len(rows),
        "page_range": page.paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1)})


@role_required(*ATTENDANCE_VIEW_ROLES)
def attendance_export(request):
    form, rows, days, start, end, today = _attendance(request)
    selectors.fill_attendance_rows(rows, days)
    headers = ["#", "O'quvchi", "Kod", "Xona", *[f"{d['date']:%d.%m} {d['label']}" for d in days],
               "Bor", "Yo'q", "Kechikdi", "Sababli"]
    data = ([n, r["student"].full_name, r["student"].code, r["stay"].room.name,
             *[(c["status"] or ("O" if c["active"] else "—")) for c in r["cells"]],
             *r["totals"].values()] for n, r in enumerate(rows, start=1))
    content = excel.build_workbook("Davomat", headers, data)
    return excel.xlsx_response(f"yotoqxona-davomat-{start:%Y-%m-%d}-{end:%Y-%m-%d}.xlsx", content)


def _parse_day(value: str | None):
    try:
        return date.fromisoformat(value or "")
    except ValueError:
        return None


@role_required(*ATTENDANCE_ROLES)
@require_POST
def attendance_mark(request):
    """Bitta katak (JS): student, date, status ('' — tozalash) → yangi jamilar."""
    day = _parse_day(request.POST.get("date"))
    try:
        student_id = int(request.POST.get("student", ""))
        if day is None:
            raise ValidationError("Sana noto'g'ri.")
        attendance_service.mark(branch=request.branch, student_id=student_id, day=day,
                        status=request.POST.get("status", ""), by=request.user)
    except (ValueError, ValidationError) as e:
        errors = e.messages if isinstance(e, ValidationError) else ["So'rov noto'g'ri."]
        return JsonResponse({"ok": False, "errors": errors}, status=400)
    return JsonResponse({"ok": True})


@role_required(*ATTENDANCE_ROLES)
def attendance_day(request):
    """«Kunlik belgilash»: bir kun uchun hamma o'quvchilar (GET — sahifa, POST — saqlash)."""
    today = timezone.localdate()
    day = min(_parse_day(request.GET.get("date") or request.POST.get("date")) or today, today)
    try:
        room = int(request.GET.get("room") or 0) or None
    except ValueError:
        room = None
    sheet = selectors.day_sheet(request.branch, day, room)
    if request.method == "POST":
        marks = {}
        for item in sheet:
            sid = item["stay"].student_id
            value = request.POST.get(f"s{sid}", "")
            if value != item["status"]:
                marks[sid] = value
        try:
            saved = attendance_service.mark_day(branch=request.branch, day=day, marks=marks, by=request.user)
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
        else:
            messages.success(request, f"{day:%d.%m.%Y} davomati saqlandi ({saved} ta o'zgarish)."
                             if marks else "O'zgarish yo'q.")
        return redirect(f"{reverse('dorm:attendance_day')}?date={day:%Y-%m-%d}" + (f"&room={room}" if room else ""))
    counts = {s: sum(1 for i in sheet if i["status"] == s) for s in DormAttendance.Status.values}
    return render(request, "dorm/attendance_day.html", {
        "day": day, "today": today, "sheet": sheet, "rooms": selectors.room_choices(request.branch), "room": room,
        "statuses": DormAttendance.Status.choices, "counts": counts,
        "unmarked": sum(1 for i in sheet if not i["status"]),
        "prev_day": day - timedelta(days=1), "next_day": day + timedelta(days=1)})
