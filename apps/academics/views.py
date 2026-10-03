import copy
from datetime import date, timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import Role
from apps.accounts.permissions import role_required
from apps.common import excel
from apps.common.forms import apply_errors, filter_menu
from apps.common.http import int_param, safe_next
from apps.core.models import AcademicYear
from apps.payroll.selectors import month_payroll, payroll_settings
from apps.people.models import Teacher

from . import selectors
from .forms import (
    BellsForm,
    ClassFilterForm,
    GroupForm,
    LessonForm,
    MembersForm,
    RemoveLessonForm,
    SchoolClassForm,
    TimetableFilterForm,
    subject_forms,
    subject_pairs,
)
from .models import ClassAttendance, Group, GroupMembership, Lesson, SchoolClass, Subject, TimeSlot, Weekday
from .panel import teacher_ctx
from .services import class_attendance, timetable
from .services import classes as class_service
from .services import groups as group_service

ACADEMIC_ROLES = (Role.HEAD_TEACHER,)
ACADEMIC_VIEW_ROLES = (*ACADEMIC_ROLES, Role.DIRECTOR)  # direktor — faqat ko'radi


def _filters(request):
    """Sukut bo'yicha joriy o'quv yili ("Barcha yillar" tanlansa — bo'sh qiymat yuboriladi)."""
    params = request.GET.copy()
    if "year" not in params:
        year = AcademicYear.current()
        params["year"] = str(year.pk) if year else ""
    form = ClassFilterForm(params)
    return form, params


@role_required(*ACADEMIC_VIEW_ROLES)
def class_list(request):
    """Sinflar va guruhlar: ikki ko'rinish (segment) — sinflar jadvali va guruh kartalari."""
    form, params = _filters(request)
    f = form.to_filters()
    view = "groups" if request.GET.get("view") == "groups" else "classes"
    active = form.active_filters() - {"year"}
    params.pop("view", None)
    ctx = {
        "form": form, "view": view, "stats": selectors.stats(request.branch, f.year), "q": f.q,
        "filter_menu": filter_menu(form, form.active_filters()), "active_filters": form.active_filters(),
        "has_filters": bool(active or f.q), "querystring": params.urlencode(),
    }
    if view == "groups":
        ctx["groups"] = list(selectors.groups_list(request.branch, f))
        ctx["count"] = len(ctx["groups"])
    else:
        ctx["classes"] = list(selectors.classes_list(request.branch, f))
        ctx["count"] = len(ctx["classes"])
    return render(request, "academics/class_list.html", ctx)


# ---------- Sinf ----------

def _get_class(request, pk) -> SchoolClass:
    try:
        return selectors.class_detail(request.branch, pk)
    except SchoolClass.DoesNotExist as e:
        raise Http404 from e


@role_required(*ACADEMIC_VIEW_ROLES)
def class_detail(request, pk):
    c = _get_class(request, pk)
    return render(request, "academics/class_detail.html", {
        "c": c, "students": selectors.class_students(c),
        "groups": list(selectors.groups_list(request.branch, selectors.ClassFilters(), school_class=c.pk)),
    })


def _class_form(request, instance=None):
    year = AcademicYear.current()
    form = SchoolClassForm(request.POST or None, instance=instance, branch=request.branch,
                           initial=None if instance else {"academic_year": year, "is_active": True})
    if request.method == "POST" and form.is_valid():
        try:
            c = class_service.save_class(instance, branch=request.branch, by=request.user, **form.cleaned_data)
        except ValidationError as e:
            apply_errors(form, e)
        else:
            messages.success(request, f"«{c.name}» sinfi saqlandi.")
            return redirect("academics:class_detail", pk=c.pk)
    return render(request, "academics/class_form.html", {"form": form, "c": instance})


@role_required(*ACADEMIC_ROLES)
def class_create(request):
    return _class_form(request)


@role_required(*ACADEMIC_ROLES)
def class_update(request, pk):
    return _class_form(request, get_object_or_404(SchoolClass, branch=request.branch, pk=pk))


@role_required(*ACADEMIC_ROLES)
@require_POST
def class_delete(request, pk):
    c = get_object_or_404(SchoolClass, branch=request.branch, pk=pk)
    if class_service.delete_class(c, by=request.user) == "deleted":
        messages.success(request, f"«{c.name}» sinfi o'chirildi.")
    else:
        messages.success(request, f"«{c.name}» sinfida o'quvchi yoki guruh tarixi bor — o'chirilmadi, "
                                  "faolsizlantirildi.")
    return redirect("academics:class_list")


# ---------- Guruh ----------

def _get_group(request, pk) -> Group:
    try:
        return selectors.group_detail(request.branch, pk)
    except Group.DoesNotExist as e:
        raise Http404 from e


@role_required(*ACADEMIC_VIEW_ROLES)
def group_detail(request, pk):
    g = _get_group(request, pk)
    ctx = {"g": g, "members": selectors.group_members(g), "history": selectors.group_history(g),
           "count": selectors.member_count(g), "today": timezone.localdate()}
    if g.kind == Group.Kind.SUBSET:
        all_classes = request.GET.get("all") == "1"
        ctx["all_classes"] = all_classes
        ctx["members_form"] = MembersForm(candidates=selectors.member_candidates(g, all_classes=all_classes),
                                          initial={"on": timezone.localdate()})
    return render(request, "academics/group_detail.html", ctx)


def _group_form(request, instance=None):
    data = request.POST or None
    initial = None
    if instance is None:
        initial = {"school_class": request.GET.get("class"), "kind": Group.Kind.WHOLE_CLASS,
                   "pay_scheme": Group.PayScheme.PER_LESSON, "rate": 2400, "capacity": 30, "is_active": True}
    form = GroupForm(data, instance=instance, branch=request.branch, initial=initial)
    rows = subject_forms(data, branch=request.branch, group=instance)
    if data is not None and form.is_valid() and all(r.is_valid() for r in rows):
        try:
            g = group_service.save_group(instance, branch=request.branch, by=request.user,
                                         subjects=subject_pairs(rows), **form.cleaned_data)
        except ValidationError as e:
            apply_errors(form, e)
        else:
            messages.success(request, f"«{g.code}» guruhi saqlandi.")
            return redirect("academics:group_detail", pk=g.pk)
    return render(request, "academics/group_form.html", {"form": form, "rows": rows, "g": instance})


@role_required(*ACADEMIC_ROLES)
def group_create(request):
    return _group_form(request)


@role_required(*ACADEMIC_ROLES)
def group_update(request, pk):
    return _group_form(request, get_object_or_404(Group, branch=request.branch, pk=pk))


@role_required(*ACADEMIC_ROLES)
@require_POST
def group_delete(request, pk):
    g = get_object_or_404(Group, branch=request.branch, pk=pk)
    back = reverse("academics:class_detail", args=[g.school_class_id])
    if group_service.delete_group(g, by=request.user) == "deleted":
        messages.success(request, f"«{g.code}» guruhi o'chirildi.")
    else:
        messages.success(request, f"«{g.code}» guruhida a'zolik tarixi bor — o'chirilmadi, faolsizlantirildi.")
    return redirect(back)


@role_required(*ACADEMIC_ROLES)
@require_POST
def group_add_members(request, pk):
    g = get_object_or_404(Group, branch=request.branch, pk=pk)
    form = MembersForm(request.POST, candidates=selectors.member_candidates(g, all_classes=True))
    if not form.is_valid():
        messages.error(request, " ".join(e for errs in form.errors.values() for e in errs))
    else:
        try:
            n = group_service.add_members(g, students=list(form.cleaned_data["students"]),
                                          on=form.cleaned_data["on"], by=request.user)
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
        else:
            messages.success(request, f"Guruhga {n} nafar o'quvchi qo'shildi.")
    return redirect("academics:group_detail", pk=g.pk)


@role_required(*ACADEMIC_ROLES)
@require_POST
def group_remove_member(request, pk, member_pk):
    m = get_object_or_404(GroupMembership.objects.select_related("student", "group"), pk=member_pk, group_id=pk,
                          group__branch=request.branch)
    try:
        group_service.remove_member(m, on=timezone.localdate(), by=request.user)
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    else:
        messages.success(request, f"{m.student.short_name} guruhdan chiqarildi (tarixda saqlanadi).")
    return redirect("academics:group_detail", pk=pk)


# ---------- Dars jadvali ----------

def _timetable_ctx(request) -> dict:
    """Filtr: o'quv yili, kim (sinf/o'qituvchi/xona), hafta. Tanlanmagan bo'lsa — to'r yo'q (bo'sh holat)."""
    year = AcademicYear.current()
    data = request.GET.copy()
    data.setdefault("by", "class")
    form = TimetableFilterForm(data, branch=request.branch, year=year)
    form.is_valid()
    d = form.cleaned_data
    year = d.get("year") or year
    today = timezone.localdate()
    week = d.get("week") or (today if year and year.start_date <= today <= year.end_date else
                             (year.start_date if year else today))
    by = d.get("by") or "class"
    target = {"class": d.get("school_class"), "teacher": d.get("teacher"), "room": d.get("room")}[by]
    timetable.ensure_slots(request.branch)
    ctx = {"form": form, "by": by, "target": target, "year": year, "today": today}
    if target:
        grid = selectors.timetable_grid(request.branch, week=week, **{
            {"class": "school_class", "teacher": "teacher", "room": "room"}[by]: target.pk})
        base = request.GET.copy()
        base.pop("week", None)
        prev_q, next_q, this_q = base.copy(), base.copy(), base.copy()
        prev_q["week"] = (grid["monday"] - timedelta(days=7)).isoformat()
        next_q["week"] = (grid["monday"] + timedelta(days=7)).isoformat()
        this_q["week"] = grid["monday"].isoformat()
        ctx.update(grid=grid, prev_q=prev_q.urlencode(), next_q=next_q.urlencode(), this_q=this_q.urlencode(),
                   can_edit=by == "class" and request.active_role.role != Role.DIRECTOR)
        if by == "class":
            ctx["cards"] = selectors.subject_cards(request.branch, target, week=grid["monday"])
            request_week = request.GET.copy()
            request_week["week"] = grid["monday"].isoformat()
            ctx["effective"] = _effective_date(_with_get(request, request_week), target.academic_year,
                                               school_class=target)
    return ctx


@role_required(*ACADEMIC_VIEW_ROLES)
def timetable_view(request):
    return render(request, "academics/timetable.html", _timetable_ctx(request))


@role_required(*ACADEMIC_VIEW_ROLES)
def timetable_print(request):
    ctx = _timetable_ctx(request)
    if not ctx.get("target"):
        return redirect("academics:timetable")
    return render(request, "academics/timetable_print.html", ctx)


def _effective_date(request, year, *, school_class=None) -> date:
    """O'zgarish qaysi sanadan: ko'rsatilgan haftaning dushanbasi (o'quv yili ichida).

    Sinf jadvali hali bo'sh bo'lsa (birinchi marta kiritilyapti) — o'quv yili boshidan: o'tgan oylar
    (masalan, sentyabr darsbay oyligi) ham to'g'ri hisoblanadi. Panelda sanani o'zgartirish mumkin.
    """
    try:
        day = date.fromisoformat(request.GET.get("week", ""))
    except ValueError:
        day = timezone.localdate()
    on = selectors.week_start(day)
    if year:
        if school_class is not None and not Lesson.objects.filter(group__school_class=school_class).exists():
            on = year.start_date
        on = min(max(on, year.start_date), year.end_date)
    return on


@role_required(*ACADEMIC_ROLES)
def lesson_panel_new(request):
    """Yon panel (fragment): bo'sh katakka dars qo'shish."""
    school_class = get_object_or_404(SchoolClass, branch=request.branch, pk=int_param(request.GET.get("class"), 0))
    slot = get_object_or_404(TimeSlot, branch=request.branch, pk=int_param(request.GET.get("slot"), 0))
    weekday = int_param(request.GET.get("weekday"), 1)
    if weekday not in Weekday.values:
        raise Http404
    groups = selectors.groups_for_cell(request.branch, school_class.academic_year, school_class=school_class.pk)
    on = _effective_date(request, school_class.academic_year, school_class=school_class)
    form = LessonForm(branch=request.branch, groups=groups, initial={
        "weekday": weekday, "slot": slot, "on": on,
        "group": groups[0] if len(groups) == 1 else None})
    subject_map = {g.pk: {"subjects": [[gs.subject_id, f"{gs.subject.name} · {gs.teacher.user.short_name}"]
                                       for gs in g.subjects.all()], "room": g.room_id} for g in groups}
    return render(request, "academics/_lesson_new.html", {
        "form": form, "school_class": school_class, "slot": slot, "weekday_label": Weekday(weekday).label,
        "subject_map": subject_map, "next": safe_next(request, request.GET.get("next"),
                                                      reverse("academics:timetable"))})


@role_required(*ACADEMIC_ROLES)
@require_POST
def lesson_create(request):
    back = safe_next(request, request.POST.get("next"), reverse("academics:timetable"))
    groups = Group.objects.filter(branch=request.branch, is_active=True)
    form = LessonForm(request.POST, branch=request.branch, groups=groups)
    if not form.is_valid():
        messages.error(request, " ".join(e for errs in form.errors.values() for e in errs))
        return redirect(back)
    d = form.cleaned_data
    try:
        lesson = timetable.add_lesson(group=d["group"], subject=d["subject"], weekday=d["weekday"], slot=d["slot"],
                                      room=d["room"] or timetable.default_room(d["group"]), on=d["on"], by=request.user)
    except ValidationError as e:
        messages.error(request, "Dars qo'shilmadi. " + " ".join(e.messages))
    else:
        messages.success(request, f"Dars qo'shildi: {lesson.group.code} · {lesson.subject.name}, "
                                  f"{lesson.get_weekday_display()} {lesson.slot.number}-dars ({d['on']:%d.%m.%Y} dan).")
    return redirect(back)


@role_required(*ACADEMIC_VIEW_ROLES)
def lesson_panel(request, pk):
    """Yon panel (fragment): dars haqida va uni olib tashlash."""
    try:
        lesson = selectors.lesson_detail(request.branch, pk)
    except Lesson.DoesNotExist as e:
        raise Http404 from e
    form = RemoveLessonForm(initial={"on": max(_effective_date(request, lesson.academic_year), lesson.valid_from)})
    return render(request, "academics/_lesson_panel.html", {
        "lesson": lesson, "form": form,
        "next": safe_next(request, request.GET.get("next"), reverse("academics:timetable"))})


@role_required(*ACADEMIC_ROLES)
@require_POST
def lesson_remove(request, pk):
    lesson = get_object_or_404(Lesson, branch=request.branch, pk=pk)
    back = safe_next(request, request.POST.get("next"), reverse("academics:timetable"))
    form = RemoveLessonForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Sanani kiriting.")
        return redirect(back)
    try:
        result = timetable.remove_lesson(lesson, on=form.cleaned_data["on"], by=request.user)
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    else:
        messages.success(request, "Dars jadvaldan olib tashlandi." if result == "deleted" else
                         f"Dars {form.cleaned_data['on']:%d.%m.%Y} dan olib tashlandi — oldingi haftalar saqlanadi.")
    return redirect(back)


@role_required(*ACADEMIC_ROLES)
def bells(request):
    """Qo'ng'iroqlar (dars vaqtlari): yon panel (GET — fragment), saqlash (POST)."""
    slots = timetable.ensure_slots(request.branch)
    back = safe_next(request, request.POST.get("next") or request.GET.get("next"), reverse("academics:timetable"))
    form = BellsForm(request.POST or None, slots=slots)
    if request.method == "POST":
        if form.is_valid():
            try:
                timetable.save_slots(request.branch, form.slot_rows(), by=request.user)
            except ValidationError as e:
                messages.error(request, " ".join(e.messages))
            else:
                messages.success(request, "Qo'ng'iroq vaqtlari saqlandi.")
        else:
            messages.error(request, "Vaqtlar noto'g'ri kiritilgan.")
        return redirect(back)
    return render(request, "academics/_bells_panel.html", {"form": form, "next": back})


def _with_get(request, params):
    """_effective_date uchun: so'rovning GET'ini boshqa parametrlar bilan (asl so'rov o'zgarmaydi)."""
    clone = copy.copy(request)
    clone.GET = params
    return clone


def _json_error(e) -> JsonResponse:
    messages_ = e.messages if isinstance(e, ValidationError) else [str(e)]
    return JsonResponse({"ok": False, "errors": messages_}, status=400)


def _drop_target(request):
    """Sudrab qo'yish so'rovidagi umumiy maydonlar: hafta kuni, dars vaqti, sana."""
    try:
        weekday = int(request.POST["weekday"])
        Weekday(weekday)
        on = date.fromisoformat(request.POST["on"])
    except (KeyError, ValueError) as e:
        raise ValidationError("Katak yoki sana noto'g'ri.") from e
    slot = TimeSlot.objects.filter(branch=request.branch, pk=int_param(request.POST.get("slot"), 0)).first()
    if slot is None:
        raise ValidationError("Dars vaqti topilmadi.")
    return weekday, slot, on


@role_required(*ACADEMIC_ROLES)
@require_POST
def lesson_place(request):
    """Fan kartasini katakka tashlash (JSON). Hovuz kartasi — barcha guruhlariga bir vaqtda."""
    try:
        weekday, slot, on = _drop_target(request)
        ids = [int(x) for x in request.POST.get("groups", "").split(",") if x.strip()]
        groups = list(Group.objects.filter(branch=request.branch, pk__in=ids, is_active=True)
                      .select_related("school_class__room", "room", "academic_year"))
        subject = Subject.objects.filter(pk=int_param(request.POST.get("subject"), 0)).first()
        if not groups or len(groups) != len(ids) or subject is None:
            raise ValidationError("Karta topilmadi — sahifani yangilang.")
        lessons = timetable.place_card(groups=groups, subject=subject, weekday=weekday, slot=slot, on=on,
                                       by=request.user)
    except (ValidationError, ValueError) as e:
        return _json_error(e)
    messages.success(request, f"{subject.name}: {Weekday(weekday).label}, {slot.number}-dars "
                              f"({len(lessons)} guruh, {on:%d.%m.%Y} dan).")
    return JsonResponse({"ok": True})


@role_required(*ACADEMIC_ROLES)
@require_POST
def lesson_move(request, pk):
    """Jadvaldagi darsni boshqa katakka sudrab ko'chirish (JSON)."""
    lesson = get_object_or_404(Lesson.objects.select_related("group__school_class", "subject", "room"),
                               branch=request.branch, pk=pk)
    try:
        weekday, slot, on = _drop_target(request)
        moved = timetable.move_lesson(lesson, weekday=weekday, slot=slot, on=on, by=request.user)
    except ValidationError as e:
        return _json_error(e)
    messages.success(request, f"{moved.subject.name} ko'chirildi: {moved.get_weekday_display()}, "
                              f"{moved.slot.number}-dars ({moved.valid_from:%d.%m.%Y} dan).")
    return JsonResponse({"ok": True})


def _grid_rows(grid, label):
    for row in grid["rows"]:
        slot = row["slot"]
        head = f"{'OBED' if slot.is_break else f'{slot.number}-dars'} {slot.start:%H:%M}–{slot.end:%H:%M}"
        yield [head, *("\n".join(label(lesson) for lesson in cell["lessons"]) for cell in row["cells"])]


@role_required(*ACADEMIC_VIEW_ROLES)
def timetable_export(request):
    """Joriy ko'rinish (sinf/o'qituvchi/xona, hafta) — Excel."""
    ctx = _timetable_ctx(request)
    if not ctx.get("target"):
        return redirect("academics:timetable")
    grid = ctx["grid"]

    def label(lesson):
        room = f" · {lesson.room.name}" if lesson.room else ""
        who = lesson.teacher.user.short_name if ctx["by"] == "class" else lesson.group.school_class.name
        return f"{lesson.subject.name} · {who}{room}"
    headers = ["Dars", *(f"{d['label']} {d['date']:%d.%m}" for d in grid["days"])]
    content = excel.build_workbook("Dars jadvali", headers, _grid_rows(grid, label))
    return excel.xlsx_response(f"dars-jadvali-{grid['monday']:%Y-%m-%d}.xlsx", content)


@role_required(*ACADEMIC_VIEW_ROLES)
def timetable_export_all(request):
    """Barcha sinflar jadvali (ko'rsatilgan hafta) — Excel: har bir dars bir qatorda."""
    try:
        week = date.fromisoformat(request.GET.get("week", ""))
    except ValueError:
        week = timezone.localdate()
    grid = selectors.timetable_grid(request.branch, week=week)
    items = []
    for row in grid["rows"]:
        for cell in row["cells"]:
            for lesson in cell["lessons"]:
                items.append(((lesson.group.school_class.name, cell["weekday"], row["slot"].number), [
                    lesson.group.school_class.name, Weekday(cell["weekday"]).label, row["slot"].number,
                    f"{row['slot'].start:%H:%M}–{row['slot'].end:%H:%M}", lesson.subject.name,
                    lesson.teacher.user.full_name, lesson.room.name if lesson.room else "", lesson.group.code]))
    rows = [r for _, r in sorted(items, key=lambda item: item[0])]
    headers = ["Sinf", "Kun", "Dars", "Vaqt", "Fan", "O'qituvchi", "Xona", "Guruh"]
    content = excel.build_workbook("Barcha sinflar", ["#", *headers], ([n, *r] for n, r in enumerate(rows, start=1)))
    return excel.xlsx_response(f"dars-jadvali-barcha-{grid['monday']:%Y-%m-%d}.xlsx", content)


# ---------- O'qituvchi paneli ----------

@role_required(Role.TEACHER)
def my_schedule(request):
    """Mening jadvalim: o'qituvchining haftalik jadvali (faqat ko'rish), hafta varaqlash."""
    today = timezone.localdate()
    ctx = teacher_ctx(request, today)
    try:
        day = date.fromisoformat(request.GET.get("week", ""))
    except ValueError:
        day = today
    monday = selectors.week_start(day)
    if ctx["teacher"]:
        grid = selectors.timetable_grid(request.branch, week=monday, teacher=ctx["teacher"].pk)
        ctx.update(grid=grid, week_days=selectors.week_day_lessons(grid))
    ctx.update(monday=monday, prev_week=monday - timedelta(days=7), next_week=monday + timedelta(days=7),
               this_week=selectors.week_start(today))
    return render(request, "academics/my_schedule.html", ctx)


@role_required(Role.TEACHER)
def my_groups(request):
    """Guruhlarim: o'qituvchining tanlov guruhlari (kartalar)."""
    ctx = teacher_ctx(request, timezone.localdate())
    if ctx["teacher"]:
        ctx["groups"] = selectors.teacher_groups(request.branch, ctx["teacher"])
    return render(request, "academics/my_groups.html", ctx)


def _my_group(request, pk):
    ctx = teacher_ctx(request, timezone.localdate())
    g = selectors.teacher_group(request.branch, ctx["teacher"], pk) if ctx["teacher"] else None
    if g is None:
        raise Http404
    return ctx, g


@role_required(Role.TEACHER)
def my_group_detail(request, pk):
    """Guruhni boshqarish: a'zolar (chiqarish) va shu sinfdan nomzodlar (biriktirish)."""
    ctx, g = _my_group(request, pk)
    candidates = selectors.member_candidates(g)
    ctx.update(g=g, members=selectors.group_members(g), candidates=candidates,
               stats=selectors.group_assign_stats(g, candidates), can_edit=True)
    return render(request, "academics/my_group_detail.html", ctx)


def _my_group_for_edit(request, pk):
    """O'qituvchi — o'z guruhi; superadmin — «Superadmin ko'rinishi»da tanlangan o'qituvchi guruhi."""
    return _my_group(request, pk)[1]


@role_required(Role.TEACHER)
@require_POST
def my_group_add(request, pk):
    g = _my_group_for_edit(request, pk)
    student = get_object_or_404(selectors.member_candidates(g), pk=int_param(request.POST.get("student"), 0))
    try:
        group_service.add_members(g, students=[student], on=timezone.localdate(), by=request.user)
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    else:
        messages.success(request, f"{student.short_name} guruhga biriktirildi.")
    return redirect("academics:my_group_detail", pk=g.pk)


@role_required(Role.TEACHER)
@require_POST
def my_group_remove(request, pk, membership_pk):
    g = _my_group_for_edit(request, pk)
    m = get_object_or_404(g.memberships.select_related("student", "group"), pk=membership_pk, left_at__isnull=True)
    try:
        group_service.remove_member(m, on=timezone.localdate(), by=request.user)
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    else:
        messages.success(request, f"{m.student.short_name} guruhdan chiqarildi — nomzodlar ro'yxatiga qaytdi.")
    return redirect("academics:my_group_detail", pk=g.pk)


# ---------- Ish haqi qoidalari ----------

GUIDE_ADVANCE_PERCENT = 30  # kalkulyatordagi boshlang'ich qiymat (o'qituvchi o'zgartira oladi)


@role_required(Role.TEACHER)
def my_salary_guide(request):
    """«Ish haqi qoidalari»: formula, shaxsiy hisob (shu oy), bitta o'quvchi ulushi va avans kalkulyatori.

    Foiz va stavkalar filial sozlamasidan (`PayrollSettings`) jonli olinadi.
    """
    today = timezone.localdate()
    ctx = teacher_ctx(request, today)
    cfg = payroll_settings(request.branch)
    ctx.update(cfg=cfg, advance_percent=GUIDE_ADVANCE_PERCENT,
               categories=[(label, cfg.category_percent(value)) for value, label in Teacher.Category.choices])
    if ctx["teacher"]:
        rows = month_payroll(request.branch, today.replace(day=1), teacher=ctx["teacher"].pk).rows
        ctx["pay"] = rows[0].pay if rows else None
    return render(request, "academics/my_salary_guide.html", ctx)


# ---------- Sinf rahbarlik ----------

HOMEROOM_TABS = ("day", "week", "month")


@role_required(Role.TEACHER)
def my_homeroom(request):
    """Sinf rahbarligi: o'qituvchi rahbar bo'lgan sinflar va bugungi davomat holati."""
    today = timezone.localdate()
    ctx = teacher_ctx(request, today)
    if ctx["teacher"]:
        ctx["classes"] = selectors.homeroom_classes(request.branch, ctx["teacher"], today)
    return render(request, "academics/my_homeroom.html", ctx)


def _homeroom(request, pk):
    today = timezone.localdate()
    ctx = teacher_ctx(request, today)
    c = selectors.homeroom_class(request.branch, ctx["teacher"], pk) if ctx["teacher"] else None
    if c is None:
        raise Http404
    return ctx, c, today


def _parse_date(value, default):
    try:
        return date.fromisoformat(value or "")
    except ValueError:
        return default


@role_required(Role.TEACHER)
def my_homeroom_class(request, pk):
    """Sinf sahifasi: kunlik davomat (belgilash), haftalik jadval, oylik statistika."""
    ctx, c, today = _homeroom(request, pk)
    tab = request.GET.get("tab", "day")
    tab = tab if tab in HOMEROOM_TABS else "day"
    day = min(_parse_date(request.GET.get("date") or request.POST.get("date"), today), today)
    if request.method == "POST":
        rows = {}
        for item in selectors.class_day_sheet(c, day):
            sid = item["student"].pk
            rows[sid] = (request.POST.get(f"s{sid}", ""), request.POST.get(f"n{sid}", ""))
        try:
            saved = class_attendance.save_day(c, day=day, rows=rows, by=request.user)
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
        else:
            messages.success(request, f"{c.name}: {day:%d.%m.%Y} davomati saqlandi ({saved} ta belgi).")
        return redirect(f"{reverse('academics:my_homeroom_class', args=[c.pk])}?date={day:%Y-%m-%d}")
    ctx.update(c=c, tab=tab, day=day, statuses=ClassAttendance.Status.choices,
               n_students=selectors.class_students(c).count())
    if tab == "day":
        ctx["sheet"] = selectors.class_day_sheet(c, day)
        ctx["unmarked"] = sum(1 for x in ctx["sheet"] if not x["mark"])
    elif tab == "week":
        monday = selectors.week_start(_parse_date(request.GET.get("week"), today))
        ctx.update(grid=selectors.timetable_grid(request.branch, week=monday, school_class=c.pk),
                   prev_week=monday - timedelta(days=7), next_week=monday + timedelta(days=7))
    else:
        month = _parse_date(f"{request.GET.get('month', '')}-01", today).replace(day=1)
        ctx.update(stats=selectors.class_month_stats(c, month, today),
                   prev_month=(month - timedelta(days=1)).replace(day=1),
                   next_month=(month + timedelta(days=32)).replace(day=1), this_month=today.replace(day=1))
    return render(request, "academics/my_homeroom_class.html", ctx)


@role_required(Role.TEACHER)
def my_homeroom_export(request, pk):
    """Oylik davomat Excel'i (o'quvchi × kun + jamilar)."""
    ctx, c, today = _homeroom(request, pk)
    month = _parse_date(f"{request.GET.get('month', '')}-01", today).replace(day=1)
    st = selectors.class_month_stats(c, month, today)
    symbols = {"B": "✓", "Y": "✗", "K": "K", "S": "S"}
    headers = ["#", "O'quvchi", *[f"{d['date']:%d} {d['label']}" for d in st["days"]], "Keldi", "Kelmadi",
               "Kechikdi", "Sababli", "Kelish %"]
    rows = ([n, r["student"].full_name, *[symbols.get(x, "") for x in r["cells"]], *r["totals"].values(),
             r["percent"] if r["percent"] is not None else ""] for n, r in enumerate(st["rows"], start=1))
    content = excel.build_workbook(f"{c.name} {month:%Y-%m}", headers, rows)
    return excel.xlsx_response(f"davomat-{c.name}-{month:%Y-%m}.xlsx", content)


@role_required(Role.TEACHER)
def teacher_dashboard(request):
    """O'qituvchi bosh sahifasi (asl tizimdagidek): bugungi darslar, o'quvchilar, haftalik darslar, guruhlar."""
    today = timezone.localdate()
    ctx = teacher_ctx(request, today)
    teacher = ctx["teacher"]
    if teacher:
        ctx.update(selectors.teacher_dashboard(request.branch, teacher, today))
    return render(request, "academics/teacher_dashboard.html", ctx)
