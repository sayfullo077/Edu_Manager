from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.domain.phone import format_phone
from apps.accounts.models import Role
from apps.accounts.permissions import role_required
from apps.common import excel
from apps.common.forms import apply_errors, filter_menu
from apps.common.http import int_param, safe_next
from apps.core.models import AcademicYear
from apps.people.models import Student

from . import selectors
from .domain.document import PLACEHOLDERS
from .forms import (
    CancelForm,
    CodeForm,
    ContractFilterForm,
    ContractForm,
    ContractTemplateForm,
    NewContractForm,
    ScanForm,
)
from .models import Contract, ContractTemplate
from .services import contracts as service
from .services import document

STAFF_ROLES = (Role.HEAD_TEACHER, Role.RECEPTION)
STAFF_VIEW_ROLES = (*STAFF_ROLES, Role.DIRECTOR)  # direktor — faqat ko'radi
PAGE_SIZE = 25


def _next(request) -> str:
    """Shartnoma sahifasiga qayerdan kelingan bo'lsa (o'quvchi kartasi, tahrirlash, ro'yxat) — o'sha joy."""
    return safe_next(request, request.POST.get("next") or request.GET.get("next"), reverse("contracts:contract_list"))


def _to_detail(request, pk):
    url = reverse("contracts:contract_detail", args=[pk])
    back = request.POST.get("next") or request.GET.get("next")
    return redirect(f"{url}?{urlencode({'next': _next(request)})}" if back else url)


def _get(request, pk) -> Contract:
    try:
        return selectors.contract_detail(request.branch, pk)
    except Contract.DoesNotExist as e:
        raise Http404 from e


@role_required(*STAFF_VIEW_ROLES)
def contract_list(request):
    form = ContractFilterForm(request.GET or None, branch=request.branch)
    values = form.values()
    page = Paginator(selectors.contracts(request.branch, **values), PAGE_SIZE).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    active = form.active_filters()
    return render(request, "contracts/contract_list.html", {
        "form": form, "q": values["q"], "status": values["status"], "page": page, "querystring": query.urlencode(),
        "filter_menu": filter_menu(form, active), "active_filters": active,
        "has_filters": bool(active or values["q"]),
        "page_range": page.paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1),
        "stats": selectors.contract_stats(request.branch),
    })


def _new_contract(request, student=None):
    """"Yangi shartnoma": o'quvchi (ro'yxatdan yoki o'quvchi kartasidan), vasiy, shablon, o'quv yili, tarif."""
    year = AcademicYear.current()
    if student is None and request.GET.get("student"):
        student = Student.objects.filter(branch=request.branch, pk=int_param(request.GET["student"], 0)).first()
    if student:
        existing = selectors.active_contract_for(student)
        if existing:
            messages.info(request, f"Bu o'quvchida amaldagi shartnoma bor: {existing.number}.")
            return redirect("contracts:contract_detail", pk=existing.pk)
    candidates = selectors.contract_candidates(request.branch, year)
    initial = {"academic_year": year, "discount_percent": 0}
    if student:
        d = service.defaults_for(student)
        initial.update(full_tariff=d.full_tariff, start_date=d.start_date)
    form = NewContractForm(request.POST or None, candidates=candidates, fixed_student=student, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = dict(form.cleaned_data)
        chosen = student or data.pop("student")
        data.pop("student", None)
        try:
            contract = service.create_contract(student=chosen, by=request.user,
                                               academic_year=data.pop("academic_year") or year, **data)
        except ValidationError as e:
            apply_errors(form, e)
        else:
            messages.success(request, f"{contract.number} shartnoma qoralamasi tuzildi. Endi vasiyga SMS kod yuboring.")
            return redirect("contracts:contract_detail", pk=contract.pk)
    return render(request, "contracts/contract_new.html", {
        "form": form, "student": student,
        "candidate_map": {} if student else selectors.candidate_map(candidates),
        "back_url": safe_next(request, request.GET.get("next"), reverse("contracts:contract_list"))})


@role_required(*STAFF_ROLES)
def contract_new(request):
    return _new_contract(request)


@role_required(*STAFF_ROLES)
def contract_create(request, student_pk):
    """O'quvchi kartasidan: o'quvchi tanlangan holda."""
    student = get_object_or_404(Student.objects.select_related("school_class"), branch=request.branch,
                                pk=student_pk)
    return _new_contract(request, student)


@role_required(*STAFF_ROLES)
def contract_update(request, pk):
    contract = _get(request, pk)
    if not contract.is_editable:
        messages.error(request, "Faqat qoralamani tahrirlash mumkin.")
        return redirect("contracts:contract_detail", pk=pk)
    form = ContractForm(request.POST or None, instance=contract)
    if request.method == "POST" and form.is_valid():
        try:
            service.update_contract(contract, by=request.user, **form.cleaned_data)
        except ValidationError as e:
            apply_errors(form, e)
        else:
            messages.success(request, "Shartnoma yangilandi.")
            return redirect("contracts:contract_detail", pk=pk)
    return render(request, "contracts/contract_form.html",
                  {"form": form, "student": contract.student, "contract": contract})


@role_required(*STAFF_VIEW_ROLES)
def contract_detail(request, pk, code_form=None, cancel_form=None, scan_form=None):
    contract = _get(request, pk)
    return render(request, "contracts/contract_detail.html", {
        "contract": contract, "back_url": _next(request), "doc": document.contract_document(contract),
        "has_next": bool(request.POST.get("next") or request.GET.get("next")),
        "code_form": code_form or CodeForm(),
        "cancel_form": cancel_form or CancelForm(),
        "scan_form": scan_form or ScanForm(),
    })


@role_required(*STAFF_ROLES)
@require_POST
def contract_send_code(request, pk):
    contract = _get(request, pk)
    try:
        service.send_confirmation_code(contract, by=request.user, ip=request.client_ip)
    except (ValidationError, service.ratelimit.RateLimited) as e:
        messages.error(request, " ".join(getattr(e, "messages", [str(e)])))
    else:
        messages.success(request, f"Tasdiqlash kodi {contract.guardian.short_name}ga SMS orqali yuborildi.")
    return _to_detail(request, pk)


@role_required(*STAFF_ROLES)
@require_POST
def contract_confirm(request, pk):
    contract = _get(request, pk)
    form = CodeForm(request.POST)
    if form.is_valid():
        try:
            service.confirm_with_code(contract, code=form.cleaned_data["code"], by=request.user,
                                      ip=request.client_ip)
        except ValidationError as e:
            apply_errors(form, e)
        except service.ratelimit.RateLimited as e:
            form.add_error("code", str(e))
        else:
            messages.success(request, f"{contract.number} shartnoma imzolandi.")
            return _to_detail(request, pk)
    return contract_detail(request, pk, code_form=form)


@role_required(*STAFF_ROLES)
@require_POST
def contract_cancel(request, pk):
    contract = _get(request, pk)
    form = CancelForm(request.POST)
    if form.is_valid():
        try:
            service.cancel_contract(contract, reason=form.cleaned_data["reason"], by=request.user)
        except ValidationError as e:
            apply_errors(form, e)
        else:
            messages.success(request, f"{contract.number} bekor qilindi.")
            return _to_detail(request, pk)
    return contract_detail(request, pk, cancel_form=form)


@role_required(*STAFF_ROLES)
@require_POST
def contract_upload_scan(request, pk):
    contract = _get(request, pk)
    form = ScanForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            service.attach_scan(contract, file=form.cleaned_data["scan"], by=request.user)
        except ValidationError as e:
            form.add_error("scan", e.messages)
        else:
            messages.success(request, "Skaner biriktirildi.")
            return _to_detail(request, pk)
    return contract_detail(request, pk, scan_form=form)


@role_required(*STAFF_VIEW_ROLES)
def contract_scan(request, pk):
    """Skaner faqat ruxsati bor xodimga, shu view orqali beriladi (to'g'ridan-to'g'ri URL yo'q)."""
    contract = _get(request, pk)
    if not contract.scan:
        raise Http404
    response = FileResponse(contract.scan.open("rb"), content_type="application/pdf",
                            filename=f"{contract.number}.pdf")
    response["Content-Disposition"] = f'inline; filename="{contract.number}.pdf"'
    response["Cache-Control"] = "private, no-store"
    return response


@role_required(*STAFF_VIEW_ROLES)
def contract_print(request, pk):
    contract = _get(request, pk)
    return render(request, "contracts/contract_print.html", {
        "contract": contract, "doc": document.contract_document(contract),
        "back_url": reverse("contracts:contract_detail", args=[contract.pk])})


EXPORT_HEADERS = ["#", "Raqami", "O'quvchi", "O'quvchi kodi", "Sinf", "Ota-ona", "Telefon", "O'quv yili",
                  "To'liq tarif", "Chegirma (%)", "Chegirma sababi", "Oylik to'lov", "Boshlanishi", "Tugashi",
                  "Holati", "Imzolangan"]
EXPORT_LIMIT = 10_000


@role_required(*STAFF_VIEW_ROLES)
def contract_export(request):
    """Joriy filtr bo'yicha shartnomalar — Excel."""
    form = ContractFilterForm(request.GET or None, branch=request.branch)
    qs = selectors.contracts(request.branch, **form.values())[:EXPORT_LIMIT]
    rows = ([n, c.number, c.student.full_name, c.student.code,
             c.class_name or getattr(c.student.school_class, "name", ""),
             c.guardian.full_name, format_phone(c.guardian.phone) if c.guardian.phone else "", c.academic_year.name,
             c.full_tariff, c.discount_percent, c.discount_reason, c.monthly_fee, c.start_date, c.end_date,
             c.get_status_display(), timezone.localtime(c.signed_at).replace(tzinfo=None) if c.signed_at else None]
            for n, c in enumerate(qs, start=1))
    content = excel.build_workbook("Shartnomalar", EXPORT_HEADERS, rows)
    return excel.xlsx_response(f"shartnomalar-{timezone.localdate():%Y-%m-%d}.xlsx", content)


# ---------- Shartnoma shablonlari ----------

@role_required(*STAFF_VIEW_ROLES)
def template_list(request):
    templates = ContractTemplate.objects.annotate(n=Count("contracts")).order_by("-is_default", "-is_active", "name")
    return render(request, "contracts/template_list.html", {"templates": templates})


def _template_form(request, instance=None):
    form = ContractTemplateForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        try:
            t = document.save_template(instance, by=request.user, **form.cleaned_data)
        except ValidationError as e:
            apply_errors(form, e)
        else:
            messages.success(request, f"«{t.name}» shabloni saqlandi. Imzolangan shartnomalar matni o'zgarmaydi.")
            return redirect("contracts:template_list")
    return render(request, "contracts/template_form.html", {
        "form": form, "t": instance, "placeholders": PLACEHOLDERS.items()})


@role_required(*STAFF_ROLES)
def template_create(request):
    return _template_form(request)


@role_required(*STAFF_ROLES)
def template_update(request, pk):
    return _template_form(request, get_object_or_404(ContractTemplate, pk=pk))
