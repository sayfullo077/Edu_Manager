from datetime import date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.domain.phone import format_phone
from apps.accounts.models import Role
from apps.accounts.permissions import role_required
from apps.common import excel
from apps.common.forms import apply_errors, filter_menu
from apps.contracts import selectors as contract_selectors
from apps.finance import selectors as finance_selectors
from apps.finance.forms import ScheduleForm

from . import selectors
from .forms import GuardianFilterForm, GuardianForm, RelationForm, StudentFilterForm, StudentForm
from .models import Guardian, Student, StudentGuardian
from .services import admission
from .services import students as student_service

STAFF_ROLES = (Role.HEAD_TEACHER, Role.RECEPTION)
PAGE_SIZE = 25


def _student_filter(request):
    params = request.GET.copy()
    params.setdefault("status", Student.Status.ACTIVE)  # sukut bo'yicha faqat faollar
    params.pop("page", None)
    filter_form = StudentFilterForm(params, branch=request.branch)
    return filter_form, params, selectors.students(request.branch, filter_form.to_filters())


@role_required(*STAFF_ROLES)
def student_list(request):
    filter_form, params, qs = _student_filter(request)
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    active = filter_form.active_filters()
    return render(request, "people/student_list.html", {
        "filter_form": filter_form,
        "filter_menu": filter_menu(filter_form, active, groups={"joined": ["joined_from", "joined_to"]}),
        "active_filters": active,
        "page": page,
        "page_range": page.paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1),
        "stats": selectors.student_stats(request.branch),
        "querystring": params.urlencode(),
        "has_filters": bool(params.get("q") or active - {"status"} or params["status"] != Student.Status.ACTIVE),
        "show_finance": request.active_role.role == Role.RECEPTION,
    })


@role_required(*STAFF_ROLES)
def student_export(request):
    """Joriy filtr bo'yicha ro'yxat — Excel."""
    _, _, qs = _student_filter(request)
    content = excel.build_workbook("O'quvchilar", student_service.EXPORT_HEADERS, student_service.export_rows(qs))
    return excel.xlsx_response(f"oquvchilar-{date.today():%Y-%m-%d}.xlsx", content)


@role_required(*STAFF_ROLES)
@require_POST
def student_delete(request, pk):
    student = get_object_or_404(Student, branch=request.branch, pk=pk)
    name = student.short_name
    result = student_service.remove_student(student, by=request.user)
    if result == "needs_settlement":
        if request.active_role.role == Role.RECEPTION:
            messages.info(request, f"{name}ning to'lov grafigi/to'lovlari bor — to'g'ridan-to'g'ri o'chirib bo'lmaydi. "
                                   "Avval o'qishdan chiqarish hisob-kitobini qiling.")
            return redirect("finance:student_withdraw", student_pk=student.pk)
        messages.error(request, f"{name}ning to'lovlari bor — o'chirish uchun Reception hisob-kitob qilishi kerak.")
        return redirect("people:student_detail", pk=student.pk)
    if result == "deleted":
        messages.success(request, f"{name} o'chirildi.")
    else:
        messages.success(request, f"{name}ning tarixi saqlanadi — o'chirilmadi, «Ketgan» holatida arxivda.")
    return redirect(f"{reverse('people:student_list')}?{request.POST.get('qs', '')}")


@role_required(*STAFF_ROLES)
def student_detail(request, pk):
    """O'quvchi kartasi: "Akademik" (profil, hujjatlar, vasiylar, guruhlar) va "To'lov" (faqat Reception)."""
    try:
        student = selectors.student_detail(request.branch, pk)
    except Student.DoesNotExist as e:
        raise Http404 from e
    finance_allowed = request.active_role.role == Role.RECEPTION  # moliya faqat Reception'ga
    view = "payment" if finance_allowed and request.GET.get("view") == "payment" else "academic"
    contracts = list(selectors.student_contracts(student))
    ctx = {
        "student": student, "view": view, "finance_allowed": finance_allowed,
        "withdrawal": getattr(student, "withdrawal", None),
        "contract": contract_selectors.active_contract_for(student), "contracts": contracts,
        "guardians": list(student.guardian_links.all()), "groups": list(student.groups.all()),
    }
    if view == "payment":
        ctx.update(finance_selectors.student_finance(student))
        ctx["schedule_form"] = ScheduleForm.for_contract(ctx["schedule_contract"], ctx["missing_months"])
    else:
        ctx["siblings"] = list(selectors.student_siblings(student))
    return render(request, "people/student_detail.html", ctx)


@role_required(*STAFF_ROLES)
def student_create(request):
    """Qabul: o'quvchi va ota-ona bitta formada, bitta tranzaksiyada."""
    is_post = request.method == "POST"
    student_form = StudentForm(request.POST if is_post else None, branch=request.branch, prefix="s",
                               initial={"joined_at": date.today(), "status": Student.Status.ACTIVE})
    guardian_form = GuardianForm(request.POST if is_post else None, prefix="g")
    relation_form = RelationForm(request.POST if is_post else None, prefix="r")
    forms_ok = is_post and all(f.is_valid() for f in (student_form, guardian_form, relation_form))
    if forms_ok:
        try:
            result = admission.admit_student(
                branch=request.branch, by=request.user, student_data=student_form.cleaned_data,
                guardian_data=guardian_form.cleaned_data, relation=relation_form.cleaned_data["relation"])
        except ValidationError as e:
            apply_errors([student_form, guardian_form], e)
        else:
            note = " Ota-ona tizimda bor edi — mavjud yozuvga biriktirildi." if result.guardian_existed else ""
            messages.success(request, f"{result.student.short_name} qabul qilindi ({result.student.code}).{note} "
                                      "Endi shartnoma tuzing.")
            return redirect("contracts:contract_create", student_pk=result.student.pk)
    return render(request, "people/admission_form.html", {
        "form": student_form, "guardian_form": guardian_form, "relation_form": relation_form,
        "suggestions": selectors.address_suggestions(request.branch)})


@role_required(*STAFF_ROLES)
def student_update(request, pk):
    """O'quvchini tahrirlash: shaxsiy ma'lumot, hujjatlar, o'qish, vasiylar — bitta "Saqlash" bilan."""
    try:
        student = selectors.student_edit(request.branch, pk)
    except Student.DoesNotExist as e:
        raise Http404 from e
    data = request.POST if request.method == "POST" else None
    form = StudentForm(data, instance=student, branch=request.branch)
    links = list(student.guardian_links.all())
    guardian_forms = [(link, GuardianForm(data, instance=link.guardian, prefix=f"g{link.pk}")) for link in links]
    add_guardian = bool(data and data.get("new-enabled") == "1")
    new_form = GuardianForm(data if add_guardian else None, prefix="new")
    missing = [r for r in (StudentGuardian.Relation.FATHER, StudentGuardian.Relation.MOTHER)
               if r not in {link.relation for link in links}]
    new_relation = RelationForm(data if add_guardian else None, prefix="new-r",
                                initial={"relation": missing[0] if missing else StudentGuardian.Relation.OTHER})

    if data is not None:
        valid = all([form.is_valid(), *(f.is_valid() for _, f in guardian_forms),
                     not add_guardian or (new_form.is_valid() and new_relation.is_valid())])
        if valid:
            try:
                admission.update_profile(
                    student, by=request.user, student_data=form.cleaned_data,
                    guardians={link.pk: f.cleaned_data for link, f in guardian_forms},
                    new_guardian=admission.NewGuardian(new_form.cleaned_data, new_relation.cleaned_data["relation"])
                    if add_guardian else None)
            except admission.ProfileError as e:
                target = {"student": form, "new": new_form, **{link.pk: f for link, f in guardian_forms}}[e.target]
                apply_errors(target, e.error)
            else:
                messages.success(request, "O'zgarishlar saqlandi.")
                return redirect("people:student_detail", pk=student.pk)

    return render(request, "people/student_form.html", {
        "form": form, "student": student, "guardian_forms": guardian_forms,
        "new_form": new_form, "new_relation": new_relation, "add_guardian": add_guardian,
        "missing_relations": [(r, StudentGuardian.Relation(r).label) for r in missing],
        "contracts": list(selectors.student_contracts(student)),
        "contract": contract_selectors.active_contract_for(student),
        "suggestions": selectors.address_suggestions(request.branch),
    })


@role_required(*STAFF_ROLES)
@require_POST
def student_detach_guardian(request, pk, link_pk):
    link = get_object_or_404(StudentGuardian.objects.select_related("guardian"),
                             pk=link_pk, student__pk=pk, student__branch=request.branch)
    try:
        admission.detach_guardian(link, by=request.user)
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    else:
        messages.success(request, f"{link.guardian.short_name} o'quvchidan ajratildi.")
    return redirect(f"{reverse('people:student_update', args=[pk])}#vasiylar")


@role_required(*STAFF_ROLES)
@require_POST
def student_toggle_flag(request, pk, field):
    student = get_object_or_404(Student, branch=request.branch, pk=pk)
    if field not in student_service.FLAG_FIELDS:
        return redirect("people:student_list")
    student_service.toggle_flag(student, field, by=request.user)
    if request.POST.get("back") == "detail":
        return redirect("people:student_detail", pk=student.pk)
    return redirect(f"{reverse('people:student_list')}?{request.POST.get('qs', '')}")


@role_required(*STAFF_ROLES)
def student_add_guardian(request, pk):
    student = get_object_or_404(Student, branch=request.branch, pk=pk)
    guardian_form = GuardianForm(request.POST or None, prefix="g")
    relation_form = RelationForm(request.POST or None, prefix="r",
                                 initial={"relation": StudentGuardian.Relation.MOTHER})
    if request.method == "POST" and guardian_form.is_valid() and relation_form.is_valid():
        try:
            guardian, existed = admission.attach_guardian(
                student, guardian_data=guardian_form.cleaned_data, by=request.user,
                relation=relation_form.cleaned_data["relation"],
                is_primary=relation_form.cleaned_data["is_primary"])
        except ValidationError as e:
            apply_errors(guardian_form, e)
        else:
            note = " (tizimda bor edi — mavjud yozuvga biriktirildi)" if existed else ""
            messages.success(request, f"{guardian.short_name} biriktirildi{note}.")
            return redirect("people:student_detail", pk=student.pk)
    return render(request, "people/guardian_attach.html", {
        "student": student, "guardian_form": guardian_form, "relation_form": relation_form})


@role_required(*STAFF_ROLES)
@require_POST
def student_set_primary_guardian(request, pk, link_pk):
    link = get_object_or_404(StudentGuardian, pk=link_pk, student__pk=pk, student__branch=request.branch)
    admission.set_primary(link, by=request.user)
    messages.success(request, f"{link.guardian.short_name} asosiy aloqa qilib belgilandi.")
    if request.POST.get("back") == "edit":
        return redirect(f"{reverse('people:student_update', args=[pk])}#vasiylar")
    return redirect("people:student_detail", pk=pk)


# ---------- Ota-onalar ----------

@role_required(*STAFF_ROLES)
def guardian_list(request):
    filter_form = GuardianFilterForm(request.GET or None)
    qs = selectors.guardians(request.branch, **filter_form.values())
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    active = filter_form.active_filters()
    return render(request, "people/guardian_list.html", {
        "filter_form": filter_form, "page": page, "q": filter_form.values()["q"],
        "filter_menu": filter_menu(filter_form, active),
        "active_filters": active, "has_filters": bool(active or filter_form.values()["q"]),
        "page_range": page.paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1),
        "stats": selectors.guardian_stats(request.branch),
        "querystring": query.urlencode(),
    })


GUARDIAN_EXPORT_HEADERS = ["#", "Familiya", "Ism", "Otasining ismi", "Telefon", "Qo'shimcha telefon", "Munosabat",
                           "Farzandlar soni", "Ish joyi", "Lavozimi", "Holati"]


@role_required(*STAFF_ROLES)
def guardian_export(request):
    """Joriy filtr bo'yicha ota-onalar — Excel. JSHSHIR/passport (shifrlangan) eksport qilinmaydi."""
    filter_form = GuardianFilterForm(request.GET or None)
    qs = selectors.guardians(request.branch, **filter_form.values())[:student_service.EXPORT_LIMIT]
    rows = ([n, g.last_name, g.first_name, g.middle_name, format_phone(g.phone) if g.phone else "",
             format_phone(g.extra_phone) if g.extra_phone else "",
             ", ".join(str(StudentGuardian.Relation(r).label) for r in g.relations if r), g.children_count,
             g.workplace, g.position, g.get_status_display()] for n, g in enumerate(qs, start=1))
    content = excel.build_workbook("Ota-onalar", GUARDIAN_EXPORT_HEADERS, rows)
    return excel.xlsx_response(f"ota-onalar-{date.today():%Y-%m-%d}.xlsx", content)


@role_required(*STAFF_ROLES)
def guardian_detail(request, pk):
    """Ota-ona kartasi: farzandlar; Reception uchun qarzdorliklar va to'lovlar tarixi ham. Tahrirlash yo'q —
    vasiy ma'lumotlari o'quvchini tahrirlash sahifasida o'zgartiriladi."""
    try:
        guardian = selectors.guardian_detail(request.branch, pk)
    except Guardian.DoesNotExist as e:
        raise Http404 from e
    links = list(guardian.child_links.all())
    finance_allowed = request.active_role.role == Role.RECEPTION
    tab = request.GET.get("tab", "children")
    if tab not in ("children", "debts", "payments") or (tab != "children" and not finance_allowed):
        tab = "children"
    ctx = {
        "guardian": guardian, "links": links, "tab": tab, "finance_allowed": finance_allowed,
        "relations": sorted({link.get_relation_display() for link in links}),
        "is_primary": any(link.is_primary for link in links),
    }
    if finance_allowed:
        fin = finance_selectors.guardian_finance([link.student_id for link in links])
        for link in links:
            link.finance = fin["per_student"][link.student_id]
        ctx.update(fin)
    return render(request, "people/guardian_detail.html", ctx)
