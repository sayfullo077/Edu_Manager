from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.academics.panel import teacher_ctx
from apps.accounts.models import Role
from apps.accounts.permissions import director_can_write, role_required
from apps.common import excel
from apps.common.http import safe_next
from apps.finance.selectors import MONTHS_UZ_FULL
from apps.people.models import Teacher

from . import selectors
from .forms import CancelPenaltyForm, PayrollSettingsForm, PenaltyForm, SalaryPaymentForm, parse_month
from .models import Penalty
from .services import payments as payment_service
from .services import penalties as penalty_service
from .services.settings import save_settings

PAYROLL_ROLES = (Role.HEAD_TEACHER,)
PAYROLL_VIEW_ROLES = (*PAYROLL_ROLES, Role.DIRECTOR)  # direktor — ko'radi; sozlamalar — o'zgartiradi


def _month(request) -> date:
    return parse_month(request.GET.get("month") or request.POST.get("month"), date.today())


def _month_ctx(month: date) -> dict:
    prev = (month.replace(day=1) - timedelta(days=1)).replace(day=1)
    nxt = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    return {"month": month, "month_label": f"{MONTHS_UZ_FULL[month.month]} {month.year}", "prev_month": prev,
            "next_month": nxt, "this_month": date.today().replace(day=1)}


@role_required(*PAYROLL_VIEW_ROLES)
def payroll_list(request):
    month = _month(request)
    data = selectors.month_payroll(request.branch, month)
    return render(request, "payroll/list.html", {
        "data": data, "totals": data.totals, **_month_ctx(month)})


EXPORT_HEADERS = ["#", "O'qituvchi", "Kod", "Fanlar", "Darslar", "O'quvchilar", "Asosiy", "Toifa",
                  "Sertifikat", "Til", "Ushlanma", "Sinf rahbarlik", "Reja (100%)", "Hisoblangan"]


@role_required(*PAYROLL_VIEW_ROLES)
def payroll_export(request):
    month = _month(request)
    data = selectors.month_payroll(request.branch, month)

    def money(p):
        return round(p.real)

    rows = [[i, r.teacher.user.full_name, r.teacher.code, r.pay.subjects_count, r.pay.lessons, r.pay.students_count,
             money(r.pay.base), money(r.pay.category_bonus), money(r.pay.certificate_bonus),
             money(r.pay.language_bonus), -money(r.pay.deductions), money(r.pay.homeroom_bonus),
             round(r.pay.total.max), money(r.pay.total)] for i, r in enumerate(data.rows, start=1)]
    t = data.totals
    rows.append(["", "Jami", "", t["subjects"], t["lessons"], t["students"], money(t["base"]),
                 money(t["category_bonus"]), money(t["certificate_bonus"]), money(t["language_bonus"]),
                 -money(t["deductions"]), money(t["homeroom_bonus"]), round(t["total"].max), money(t["total"])])
    content = excel.build_workbook(f"Oylik {month:%Y-%m}", EXPORT_HEADERS, rows)
    return excel.xlsx_response(f"oylik-{month:%Y-%m}.xlsx", content)


def _teacher_pay(request, pk):
    teacher = get_object_or_404(Teacher.objects.select_related("user"), branch=request.branch, pk=pk)
    month = _month(request)
    data = selectors.month_payroll(request.branch, month, teacher=teacher.pk)
    if not data.rows:
        raise Http404
    return teacher, month, data.rows[0].pay


@role_required(*PAYROLL_VIEW_ROLES)
def payroll_teacher(request, pk):
    teacher, month, pay = _teacher_pay(request, pk)
    payments = list(selectors.teacher_payments(request.branch, teacher, month))
    return render(request, "payroll/teacher.html", {
        "teacher": teacher, "pay": pay, **_month_ctx(month), "payments": payments,
        "status": selectors.payment_status(pay.total.real, sum((p.amount for p in payments), Decimal("0"))),
        "penalties": selectors.teacher_penalties(request.branch, teacher, month),
        "penalty_form": PenaltyForm(), "cancel_form": CancelPenaltyForm(),
        "payment_form": SalaryPaymentForm(initial={"paid_on": date.today()})})


@role_required(*PAYROLL_VIEW_ROLES)
def payroll_teacher_export(request, pk):
    """O'qituvchi oyligi tafsiloti: har qator (guruh fani / sinf rahbarlik) va o'quvchi bo'yicha."""
    teacher, month, pay = _teacher_pay(request, pk)
    rows = []
    for item in pay.items:
        line = item["line"]
        scheme = f"Darsbay ({line.lessons} dars)" if line.per_lesson else "Belgilangan"
        for s, a in line.rows:
            rows.append([line.class_name, line.subject_name, line.group_code, scheme, s.name, round(s.full),
                         round(s.amount), round(s.paid), round(a.max), round(a.real)])
        rows.append(["", "", "", "Ustama / ushlanma", "", "", "", "", round(item["bonus"].max - item["deduction"].max),
                     round(item["bonus"].real - item["deduction"].real)])
    rate = pay.rates.homeroom_rate
    for h in pay.homerooms:
        for s in h.students:
            r = s.ratio
            rows.append([h.class_name, "Sinf rahbarlik", "", "", s.name, round(s.full), round(s.amount), round(s.paid),
                         round(r.max * rate), round(r.real * rate)])
    rows.append(["", "", "", "", "Jami", "", "", "", round(pay.total.max), round(pay.total.real)])
    headers = ["Sinf", "Fan", "Guruh", "Turi", "O'quvchi", "To'liq tarif", "To'lashi kerak", "To'lagan", "Reja",
               "Haqiqiy"]
    content = excel.build_workbook(f"{teacher.code} {month:%Y-%m}", headers, rows)
    return excel.xlsx_response(f"oylik-{teacher.code}-{month:%Y-%m}.xlsx", content)


@role_required(*PAYROLL_ROLES)
@require_POST
def salary_pay(request, pk):
    teacher = get_object_or_404(Teacher.objects.select_related("user"), branch=request.branch, pk=pk)
    month = _month(request)
    back = f"{reverse('payroll:teacher', args=[teacher.pk])}?month={month:%Y-%m}"
    form = SalaryPaymentForm(request.POST)
    if not form.is_valid():
        messages.error(request, "To'lov ma'lumotlarini to'g'ri kiriting.")
        return redirect(back)
    try:
        p = payment_service.pay_salary(branch=request.branch, teacher=teacher, month=month, by=request.user,
                                       **form.cleaned_data)
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    else:
        messages.success(request, f"{p.get_kind_display()} berildi: {p.amount:,.0f} so'm.".replace(",", " "))
    return redirect(back)


@role_required(*PAYROLL_ROLES)
@require_POST
def penalty_add(request, pk):
    teacher = get_object_or_404(Teacher, branch=request.branch, pk=pk)
    month = _month(request)
    back = f"{reverse('payroll:teacher', args=[teacher.pk])}?month={month:%Y-%m}"
    form = PenaltyForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Jarima summasi va sababini to'g'ri kiriting.")
        return redirect(back)
    try:
        penalty_service.add_penalty(branch=request.branch, teacher=teacher, month=month, by=request.user,
                                    **form.cleaned_data)
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    else:
        messages.success(request, "Jarima qo'shildi.")
    return redirect(back)


@role_required(*PAYROLL_ROLES)
@require_POST
def penalty_cancel(request, pk):
    penalty = get_object_or_404(Penalty, branch=request.branch, pk=pk)
    back = f"{reverse('payroll:teacher', args=[penalty.teacher_id])}?month={penalty.month:%Y-%m}"
    form = CancelPenaltyForm(request.POST)
    try:
        if not form.is_valid():
            raise ValidationError("Bekor qilish sababini yozing.")
        penalty_service.cancel_penalty(penalty, reason=form.cleaned_data["reason"], by=request.user)
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    else:
        messages.success(request, "Jarima bekor qilindi.")
    return redirect(back)


@role_required(*PAYROLL_VIEW_ROLES)
@director_can_write
def payroll_settings(request):
    """Ustama foizlari va sinf rahbarlik summasi: yon panel (GET — fragment), saqlash (POST)."""
    obj = selectors.payroll_settings(request.branch)
    back = safe_next(request, request.POST.get("next") or request.GET.get("next"), reverse("payroll:list"))
    form = PayrollSettingsForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            try:
                save_settings(obj, form.cleaned_data)
            except ValidationError as e:
                messages.error(request, " ".join(e.messages))
            else:
                messages.success(request, "Ish haqi sozlamalari saqlandi.")
        else:
            messages.error(request, "Qiymatlar noto'g'ri: foiz 0–100, summa manfiy emas.")
        return redirect(back)
    return render(request, "payroll/_settings_panel.html", {"form": form, "next": back})


# ---------- O'qituvchi: Oyligim (olingan oyliklar) ----------

@role_required(Role.TEACHER)
def my_salary(request):
    """O'qituvchining o'z oyligi: shu oy hisobi (real / max / berilgan / qoldiq) va olingan pullar tarixi."""
    today = date.today()
    ctx = teacher_ctx(request, today)
    teacher = ctx["teacher"]
    if teacher:
        month = today.replace(day=1)
        rows = selectors.month_payroll(request.branch, month, teacher=teacher.pk).rows
        pay = rows[0].pay if rows else None
        paid = sum((p.amount for p in selectors.teacher_payments(request.branch, teacher, month)), Decimal("0"))
        ctx.update(history=selectors.teacher_payment_history(request.branch, teacher), pay=pay,
                   status=selectors.payment_status(pay.total.real, paid) if pay else None, **_month_ctx(month))
    return render(request, "payroll/my_salary.html", ctx)
