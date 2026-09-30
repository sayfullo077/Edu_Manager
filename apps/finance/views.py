from datetime import datetime
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import Role
from apps.accounts.permissions import role_required
from apps.common import excel
from apps.common.charts import donut, dual_line_chart, ring
from apps.common.forms import apply_errors, filter_menu
from apps.common.http import safe_next
from apps.common.templatetags.ui import money
from apps.people.models import Student

from . import selectors
from .forms import (
    BudgetLimitForm,
    CashCloseForm,
    DebtorFilterForm,
    ExpenseForm,
    InvoiceFilterForm,
    PaymentFilterForm,
    PaymentForm,
    PeriodForm,
    ReverseForm,
    ScheduleForm,
    TransactionFilterForm,
    WithdrawalDatesForm,
    WithdrawalForm,
)
from .models import Account, ExpenseCategory, Invoice, Payment, Transaction, Withdrawal
from .services import cash, expenses, invoices, ledger, payments, withdrawal

FINANCE_ROLES = (Role.RECEPTION,)
# Faqat ko'rish (o'quvchi kartasidagi "To'lov" bo'limi, kvitansiya, grafik Excel'i) — Zavuch ham
FINANCE_VIEW_ROLES = (Role.RECEPTION, Role.HEAD_TEACHER)
PAGE_SIZE = 25
INVOICE_EXPORT_HEADERS = ["Oy", "Hisob (to'liq tarif)", "Chegirma", "Kechilgan", "To'lanishi kerak",
                          "To'langan", "Qoldiq", "Holati"]


def _month_param(request):
    try:
        return datetime.strptime(request.GET.get("month", ""), "%Y-%m").date()
    except ValueError:
        return timezone.localdate().replace(day=1)


def _dashboard_context(request, month, *, expense_form=None, drawer_row=None) -> dict:
    ctx = selectors.reception_dashboard(request.branch, month)
    ctx["budget_page_enabled"] = settings.BUDGET_PAGE_ENABLED
    s = ctx["summary"].statuses
    ctx["donut"] = donut([
        ("To'langan", s["paid"], "var(--success)"), ("Qisman", s["partial"], "var(--info)"),
        ("Kutilmoqda", s["pending"], "var(--chart-amber)"), ("Muddati o'tgan", s["overdue"], "var(--danger)"),
    ])
    ctx["trend_chart"] = dual_line_chart(ctx["trend"], "total", "left")
    ctx["ring"] = ring(ctx["budget"]["percent"])
    ctx["months"] = selectors.budget_months(request.branch)
    ctx["month_value"] = ctx["month"].strftime("%Y-%m")
    ctx["expense_form"] = expense_form or ExpenseForm()
    ctx["drawer_row"] = drawer_row  # xato bo'lsa yon panel ochiq holda qayta chiziladi
    ctx["cash_open"] = cash.current_session(request.branch) is not None
    return ctx


@role_required(*FINANCE_ROLES)
def dashboard(request):
    return render(request, "finance/dashboard.html", _dashboard_context(request, _month_param(request)))


@role_required(*FINANCE_ROLES)
def payment_create(request, student_pk):
    student = get_object_or_404(Student, branch=request.branch, pk=student_pk)
    # O'qish yoki yotoqxona to'lovi (?category=dorm) — FIFO faqat shu turdagi oylarga taqsimlanadi
    category = request.POST.get("category") or request.GET.get("category")
    category = category if category in Invoice.Category.values else Invoice.Category.TUITION
    debt = payments.outstanding(student, category)
    unpaid = student.invoices.filter(category=category,
                                     status__in=[Invoice.Status.PENDING, Invoice.Status.PARTIAL]).order_by("month")
    form = PaymentForm(request.POST or None, initial={"amount": int(unpaid[0].remaining) if unpaid else None})
    back = safe_next(request, request.POST.get("next") or request.GET.get("next"),
                     f"{reverse('people:student_detail', args=[student.pk])}?view=payment")
    if request.method == "POST" and form.is_valid():
        try:
            payment = payments.accept_payment(student=student, by=request.user, category=category,
                                              **form.payment_kwargs())
        except ValidationError as e:
            apply_errors(form, e)
        else:
            messages.success(request, f"To'lov qabul qilindi: {payment.number}.")
            if request.POST.get("print"):  # "Kvitansiya chop etish" — to'g'ridan-to'g'ri kvitansiyaga
                return redirect(f"{reverse('finance:payment_receipt', args=[payment.pk])}?{urlencode({'next': back})}")
            return redirect(back)
    return render(request, "finance/payment_form.html", {
        "form": form, "student": student, "debt": debt, "unpaid": unpaid[:12], "back_url": back,
        "category": category, "category_label": Invoice.Category(category).label,
        "session": cash.current_session(request.branch)})


@role_required(*FINANCE_ROLES)
@require_POST
def payment_reverse(request, pk):
    payment = get_object_or_404(Payment, branch=request.branch, pk=pk)
    form = ReverseForm(request.POST)
    if form.is_valid():
        try:
            payments.reverse_payment(payment, reason=form.cleaned_data["reason"], by=request.user)
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
        else:
            messages.success(request, f"{payment.number} storno qilindi.")
    else:
        messages.error(request, "Storno sababini yozing.")
    return redirect(f"{reverse('people:student_detail', args=[payment.student_id])}?view=payment")


@role_required(*FINANCE_ROLES)
def cashbox(request):
    """Kirim → Kassa: qoldiqlar, sessiya, bugungi/oylik kirim-chiqim, to'lov turlari kesimi. ?date= — boshqa kun."""
    session = cash.current_session(request.branch)
    today = timezone.localdate()
    try:
        day = min(datetime.strptime(request.GET.get("date", ""), "%Y-%m-%d").date(), today)
    except ValueError:
        day = today
    start, end = selectors.day_bounds(day)
    close_form = CashCloseForm(request.POST or None)
    if request.method == "POST" and session and close_form.is_valid():
        closed = cash.close_session(session, counted=close_form.cleaned_data["counted"], by=request.user,
                                    note=close_form.cleaned_data["note"])
        diff = closed.difference
        note = f" Tafovut: {'+' if diff > 0 else '−'}{money(abs(diff))} so'm." if diff else " Tafovut yo'q."
        messages.success(request, "Kassa yopildi." + note)
        return redirect("finance:cashbox")
    return render(request, "finance/cashbox.html", {
        "session": session, "close_form": close_form, "is_today": day == today,
        "o": selectors.cashbox_overview(request.branch, day),
        "cash_balance": ledger.balance(ledger.get_account(request.branch, Account.Kind.CASH)),
        "transactions": (Transaction.objects.filter(branch=request.branch, occurred_at__range=(start, end))
                         .select_related("account", "payment__student", "expense__category")[:100]),
        "last_sessions": request.branch.cash_sessions.exclude(closed_at=None).select_related("closed_by")[:5],
    })


@role_required(*FINANCE_ROLES)
@require_POST
def cashbox_open(request):
    try:
        cash.open_session(request.branch, by=request.user)
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    else:
        messages.success(request, "Kassa ochildi.")
    return redirect(request.POST.get("next") if request.POST.get("next", "").startswith("/students/")
                    else "finance:cashbox")


@role_required(*FINANCE_ROLES)
def expense_create(request):
    """Asosan dashboard'dagi yon paneldan POST qilinadi; GET — JS o'chiq bo'lsa zaxira sahifa."""
    category = ExpenseCategory.objects.filter(pk=request.POST.get("category") or request.GET.get("category") or 0,
                                              is_active=True).first()
    form = ExpenseForm(request.POST or None, initial={"category": category})
    from_drawer = request.POST.get("from") == "drawer"
    if request.method == "POST" and form.is_valid():
        try:
            expense = expenses.record_expense(branch=request.branch, by=request.user, **form.cleaned_data)
        except ValidationError as e:
            apply_errors(form, e)
        else:
            messages.success(request, f"Chiqim saqlandi: {expense.category.name} — {money(expense.amount)} so'm.")
            return redirect(f"{reverse('finance:dashboard')}?month={expense.spent_at:%Y-%m}")
    if from_drawer:
        month = timezone.localdate().replace(day=1)
        b = selectors.budget(request.branch, month)
        row = next((r for r in b["fixed"] + b["normative"] if category and r.category == category), None)
        ctx = _dashboard_context(request, month, expense_form=form, drawer_row=row)
        return render(request, "finance/dashboard.html", ctx, status=400)
    return render(request, "finance/expense_form.html",
                  {"form": form, "session": cash.current_session(request.branch)})


@role_required(*FINANCE_ROLES)
def budget_edit(request):
    if not settings.BUDGET_PAGE_ENABLED:  # hozircha yopiq — to'g'ridan-to'g'ri manzil ham "tayyorlanmoqda"ga
        return redirect("core:section", slug="budget")
    month = _month_param(request)
    data = selectors.budget(request.branch, month)
    rows = data["fixed"] + data["normative"]
    form = BudgetLimitForm(request.POST or None, rows=rows)
    if request.method == "POST" and form.is_valid():
        for row in rows:
            expenses.set_limit(branch=request.branch, category=row.category, month=month, by=request.user,
                               limit=form.cleaned_data[f"limit_{row.category.pk}"])
        messages.success(request, "Byudjet limitlari saqlandi.")
        return redirect(f"{reverse('finance:dashboard')}?month={month:%Y-%m}")
    groups = [("Doimiy xarajatlar", [(r, form[f"limit_{r.category.pk}"]) for r in data["fixed"]]),
              ("Normativ xarajatlar", [(r, form[f"limit_{r.category.pk}"]) for r in data["normative"]])]
    return render(request, "finance/budget_form.html", {
        "form": form, "groups": groups, "month": month,
        "month_label": f"{selectors.MONTHS_UZ_FULL[month.month]} {month.year}"})


@role_required(*FINANCE_VIEW_ROLES)
def student_invoices_export(request, student_pk):
    """O'quvchining to'lov grafigi — Excel (O'quvchi kartasi → To'lov → Excel)."""
    student = get_object_or_404(Student, branch=request.branch, pk=student_pk)
    data = selectors.student_finance(student)
    rows = ([f"{i.month:%Y-%m}", i.full_amount, i.discount, i.waived, i.amount, i.paid, i.remaining,
             i.get_status_display()] for i in data["invoices"])
    content = excel.build_workbook(student.short_name, INVOICE_EXPORT_HEADERS, rows)
    return excel.xlsx_response(f"{student.code}-tolov-grafigi.xlsx", content)



@role_required(*FINANCE_ROLES)
def student_withdraw(request, student_pk):
    """O'qishdan chiqarish: sana → hisob-kitob (ko'rib chiqish) → tasdiqlash. Rasmiylashtirilgan bo'lsa — hujjat."""
    student = get_object_or_404(Student.objects.select_related("school_class"), branch=request.branch,
                                pk=student_pk)
    record = Withdrawal.objects.filter(student=student).select_related("created_by", "account").first()
    if record:
        lines = record.lines.select_related("invoice").order_by("invoice__month", "invoice__category")
        return render(request, "finance/withdrawal.html", {"student": student, "record": record, "lines": lines})

    is_post = request.method == "POST"
    source = request.POST if is_post else request.GET
    dates = WithdrawalDatesForm(source if "left_on" in source else {"left_on": timezone.localdate()})
    plan = None
    if dates.is_valid():
        try:
            plan = withdrawal.calculate(student, left_on=dates.cleaned_data["left_on"],
                                        dorm_left_on=dates.cleaned_data["dorm_left_on"])
        except ValidationError as e:
            apply_errors(dates, e)

    form = WithdrawalForm(request.POST if is_post else None, initial={
        **(dates.cleaned_data if plan else {}), "refund_method": Withdrawal.RefundMethod.CASH,
        "expected_refund": plan.refund if plan else 0})
    if is_post and plan and form.is_valid():
        d = form.cleaned_data
        try:
            withdrawal.withdraw(student, left_on=d["left_on"], dorm_left_on=d["dorm_left_on"], reason=d["reason"],
                                note=d["note"], refund_method=d["refund_method"],
                                expected_refund=d["expected_refund"], by=request.user)
        except ValidationError as e:
            apply_errors(form, e)
        else:
            messages.success(request, f"{student.short_name} o'qishdan chiqarildi, hisob-kitob yopildi.")
            return redirect("finance:student_withdraw", student_pk=student.pk)

    return render(request, "finance/withdrawal.html", {
        "student": student, "dates": dates, "form": form, "plan": plan,
        "cash_open": cash.current_session(request.branch) is not None,
    })


@role_required(*FINANCE_ROLES)
@require_POST
def schedule_create(request, student_pk):
    """"Grafik" oynasi: keyingi oylarni oldindan yaratish."""
    student = get_object_or_404(Student, branch=request.branch, pk=student_pk)
    contract = student.contracts.filter(status="signed").order_by("-start_date").first()
    back = f"{reverse('people:student_detail', args=[student.pk])}?view=payment#grafik"
    form = ScheduleForm(request.POST)
    if not contract:
        messages.error(request, "Imzolangan shartnoma yo'q — grafik yaratib bo'lmaydi.")
    elif form.is_valid():
        d = form.cleaned_data
        try:
            created = invoices.extend_schedule(contract, start_month=d["start_month"], months=d["months"],
                                               due_day=d["due_date"].day if d["due_date"] else None,
                                               by=request.user)
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
        else:
            months = ", ".join(f"{i.month:%Y-%m}" for i in created)
            messages.success(request, f"Grafik yaratildi: {months}.")
    else:
        messages.error(request, "Grafik ma'lumotlari noto'g'ri: " + "; ".join(
            f"{form.fields[k].label}: {' '.join(v)}" if k in form.fields else " ".join(v)
            for k, v in form.errors.items()))
    return redirect(back)


@role_required(*FINANCE_VIEW_ROLES)
def payment_receipt(request, pk):
    """To'lov kvitansiyasi (chop etish uchun). Storno qilingan bo'lsa ham ko'rinadi — belgisi bilan."""
    payment = get_object_or_404(
        Payment.objects.select_related("student__school_class", "branch", "received_by", "reversed_by")
        .prefetch_related("allocations__invoice"), branch=request.branch, pk=pk)
    fallback = f"{reverse('people:student_detail', args=[payment.student_id])}?view=payment"
    return render(request, "finance/receipt.html", {
        "payment": payment, "back_url": safe_next(request, request.GET.get("next"), fallback),
        "trx": payment.transactions.filter(kind=Transaction.Kind.PAYMENT).first(),
    })


@role_required(*FINANCE_ROLES)
def payment_list(request):
    """Kirim → To'lovlar: qabul qilingan to'lovlar tarixi. Sukut bo'yicha bugungi."""
    form = PaymentFilterForm(request.GET or None, branch=request.branch)
    filters = form.to_filters()
    qs = selectors.payments_list(request.branch, filters)
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    if not form.is_bound:  # Excel va sahifalash bugungi sanalar bilan ishlasin
        query.update({"date_from": filters.date_from.isoformat(), "date_to": filters.date_to.isoformat()})
    return render(request, "finance/payment_list.html", {
        "form": form, "filters": filters, "page": page, "querystring": query.urlencode(),
        "page_range": page.paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1),
        "stats": selectors.payments_stats(request.branch, qs, filters),
    })


PAYMENT_EXPORT_HEADERS = ["#", "Kvitansiya", "Sana", "O'quvchi", "Kodi", "Sinf", "Summa", "To'lov turi", "Karta",
                          "Qabul qildi", "Holati", "Storno sababi", "Izoh"]


@role_required(*FINANCE_ROLES)
def payment_export(request):
    form = PaymentFilterForm(request.GET or None, branch=request.branch)
    qs = selectors.payments_list(request.branch, form.to_filters())[:10_000]
    rows = ([n, p.number, timezone.localtime(p.paid_at).replace(tzinfo=None), p.student.full_name, p.student.code,
             getattr(p.student.school_class, "name", ""), p.amount, p.get_method_display(),
             p.get_card_network_display() if p.card_network else "", p.received_by.full_name,
             "Muvaffaqiyatli" if p.status == Payment.Status.OK else "Storno", p.reverse_reason, p.note]
            for n, p in enumerate(qs, start=1))
    content = excel.build_workbook("To'lovlar", PAYMENT_EXPORT_HEADERS, rows)
    return excel.xlsx_response(f"tolovlar-{timezone.localdate():%Y-%m-%d}.xlsx", content)


@role_required(*FINANCE_ROLES)
def transaction_list(request):
    """Kirim → Tranzaksiyalar: barcha kirim, chiqim, storno va qaytarish harakatlari (jurnal)."""
    form = TransactionFilterForm(request.GET or None, branch=request.branch)
    filters = form.to_filters()
    qs = selectors.transactions_list(request.branch, filters)
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    if not form.is_bound:
        query.update({"date_from": filters.date_from.isoformat(), "date_to": filters.date_to.isoformat()})
    return render(request, "finance/transaction_list.html", {
        "form": form, "filters": filters, "page": page, "querystring": query.urlencode(),
        "page_range": page.paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1),
        "stats": selectors.transactions_stats(qs),
    })


TRANSACTION_STATUS_LABELS = {"ok": "Muvaffaqiyatli", "cancelled": "Bekor qilingan", "storno": "Storno"}
TRANSACTION_EXPORT_HEADERS = ["ID", "Sana", "Turi", "Kategoriya", "To'lov turi", "Karta tarmog'i", "Summa",
                              "Komissiya", "Sof", "Kvitansiya", "O'quvchi", "Izoh", "Filial", "Yaratuvchi", "Status"]


@role_required(*FINANCE_ROLES)
def transaction_export(request):
    form = TransactionFilterForm(request.GET or None, branch=request.branch)
    qs = selectors.transactions_list(request.branch, form.to_filters())[:20_000]

    def row(t):
        sign = 1 if t.direction == Transaction.Direction.IN else -1
        p = t.payment
        network = p.get_card_network_display() if p and p.card_network else ""
        return [f"TRX-{t.pk}", timezone.localtime(t.occurred_at).replace(tzinfo=None), t.get_direction_display(),
                t.category_label, t.account.get_kind_display(), network, sign * t.amount, t.commission,
                sign * t.net, p.number if p else "", p.student.full_name if p else "", t.description, t.branch.name,
                t.created_by.full_name, TRANSACTION_STATUS_LABELS[t.status_key]]
    content = excel.build_workbook("Tranzaksiyalar", TRANSACTION_EXPORT_HEADERS, (row(t) for t in qs))
    return excel.xlsx_response(f"tranzaksiyalar-{timezone.localdate():%Y-%m-%d}.xlsx", content)


@role_required(*FINANCE_ROLES)
def bank_account(request):
    """Kirim → Bank hisobi: bank o'tkazmalari, terminal va ichki o'tkazmalar holati."""
    form = PeriodForm(request.GET or None)
    date_from, date_to = form.period()
    form.initial = {"date_from": date_from, "date_to": date_to}  # sukut sanalar maydonlarda ko'rinsin
    o = selectors.bank_overview(request.branch, date_from, date_to)
    page = Paginator(o["transactions"], 30).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    if not form.is_bound:
        query.update({"date_from": date_from.isoformat(), "date_to": date_to.isoformat()})
    return render(request, "finance/bank_account.html", {
        "form": form, "date_from": date_from, "date_to": date_to, "o": o, "page": page,
        "querystring": query.urlencode(),
        "page_range": page.paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1),
    })


@role_required(*FINANCE_ROLES)
def invoice_list(request):
    """Kirim → To'lov grafiklari: barcha o'quvchilarning oylik hisoblari."""
    form = InvoiceFilterForm(request.GET or None, branch=request.branch)
    qs = selectors.invoices_list(request.branch, form.to_filters())
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    active = form.active_filters()
    q = form.data.get("q", "")
    return render(request, "finance/invoice_list.html", {
        "form": form, "page": page, "querystring": query.urlencode(), "q": q,
        "page_range": page.paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1),
        "stats": selectors.invoices_stats(qs), "today": timezone.localdate(),
        "filter_menu": filter_menu(form, active), "active_filters": active, "has_filters": bool(active or q),
    })


INVOICE_LIST_EXPORT_HEADERS = ["#", "O'quvchi", "Kodi", "Sinf", "Oy", "Jami", "Chegirma", "Kechilgan",
                               "To'lanishi kerak", "To'langan", "Qoldiq", "Muddat", "Holati"]


@role_required(*FINANCE_ROLES)
def invoice_export(request):
    form = InvoiceFilterForm(request.GET or None, branch=request.branch)
    qs = selectors.invoices_list(request.branch, form.to_filters())[:20_000]
    rows = ([n, i.student.full_name, i.student.code, getattr(i.student.school_class, "name", ""), f"{i.month:%Y-%m}",
             i.gross, i.discount, i.waived, i.amount, i.paid, i.remaining, i.due_date,
             i.get_status_display()] for n, i in enumerate(qs, start=1))
    content = excel.build_workbook("To'lov grafiklari", INVOICE_LIST_EXPORT_HEADERS, rows)
    return excel.xlsx_response(f"tolov-grafiklari-{timezone.localdate():%Y-%m-%d}.xlsx", content)



@role_required(*FINANCE_ROLES)
def debtor_list(request):
    """Kirim → Qarzdorlar: kelgan oylar bo'yicha qarzi bor o'quvchilar (qoldiq kamayishi bo'yicha)."""
    form = DebtorFilterForm(request.GET or None, branch=request.branch)
    return render(request, "finance/debtor_list.html", {
        **debtor_list_context(request, form), "title": "Qarzdorlar",
        "list_url_name": "finance:debtor_list", "export_url_name": "finance:debtor_export"})


def debtor_list_context(request, form) -> dict:
    """Qarzdorlar sahifasi konteksti — o'qish (Kirim) va yotoqxona uchun umumiy."""
    filters = form.to_filters()
    qs = selectors.debtors(request.branch, filters)
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    active = form.active_filters()
    q = form.data.get("q", "")
    return {
        "form": form, "page": page, "querystring": query.urlencode(), "q": q, "category": filters.category,
        "page_range": page.paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1),
        "stats": selectors.debtors_stats(request.branch, filters, qs),
        "filter_menu": filter_menu(form, active), "active_filters": active, "has_filters": bool(active or q),
    }


DEBTOR_EXPORT_HEADERS = ["#", "O'quvchi", "Kodi", "Sinf", "Qarzdor oylar", "Jami", "To'langan", "Qoldiq",
                         "Oxirgi to'lov", "Oxirgi to'lov sanasi"]


def debtor_export_rows(qs):
    return ([n, s.full_name, s.code, getattr(s.school_class, "name", ""), s.debt_months, s.total, s.paid_sum,
             s.remaining, s.last_amount, timezone.localtime(s.last_paid_at).replace(tzinfo=None) if s.last_paid_at
             else None] for n, s in enumerate(qs, start=1))


@role_required(*FINANCE_ROLES)
def debtor_export(request):
    form = DebtorFilterForm(request.GET or None, branch=request.branch)
    qs = selectors.debtors(request.branch, form.to_filters())[:20_000]
    content = excel.build_workbook("Qarzdorlar", DEBTOR_EXPORT_HEADERS, debtor_export_rows(qs))
    return excel.xlsx_response(f"qarzdorlar-{timezone.localdate():%Y-%m-%d}.xlsx", content)


@role_required(*FINANCE_ROLES)
def debtor_panel(request, student_pk, kind):
    """Qarzdorlar yon paneli (fragment): kind = "info" (ma'lumot) yoki "pay" (to'lov qabul qilish)."""
    student = get_object_or_404(Student.objects.select_related("school_class"), branch=request.branch, pk=student_pk)
    category = request.GET.get("category")
    category = category if category in Invoice.Category.values else Invoice.Category.TUITION
    card = selectors.student_debt_card(student, category)
    fallback = reverse("dorm:debtor_list" if category == Invoice.Category.DORM else "finance:debtor_list")
    ctx = {"student": student, **card, "category": category,
           "next": safe_next(request, request.GET.get("next"), fallback)}
    if kind == "pay":
        ctx["form"] = PaymentForm(initial={"amount": int(card["remaining"]) or None,
                                           "paid_on": timezone.localdate()})
        ctx["session"] = cash.current_session(request.branch)
        return render(request, "finance/_debtor_pay.html", ctx)
    return render(request, "finance/_debtor_info.html", ctx)
