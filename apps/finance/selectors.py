"""Moliya o'qish so'rovlari va Reception dashboard ko'rsatkichlari."""

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, DecimalField, F, OuterRef, Prefetch, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.core.models import AcademicYear
from apps.people.models import Student, Teacher

from .models import Account, BudgetLimit, CashSession, Expense, ExpenseCategory, Invoice, Payment, Transaction
from .services import invoices as invoices_service
from .services import ledger

ZERO = Decimal("0")
MONTHS_UZ = ["", "Yan", "Fev", "Mar", "Apr", "May", "Iyun", "Iyul", "Avg", "Sen", "Okt", "Noy", "Dek"]
MONTHS_UZ_FULL = ["", "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr",
                  "Noyabr", "Dekabr"]


def _dsum(expr, **filter_kw):
    return Coalesce(Sum(expr, filter=Q(**filter_kw) if filter_kw else None), ZERO, output_field=DecimalField())


def month_bounds(month: date) -> tuple[datetime, datetime]:
    start = timezone.make_aware(datetime.combine(month.replace(day=1), time.min))
    last = calendar.monthrange(month.year, month.month)[1]
    end = timezone.make_aware(datetime.combine(month.replace(day=last), time.max))
    return start, end


def day_bounds(day: date) -> tuple[datetime, datetime]:
    return (timezone.make_aware(datetime.combine(day, time.min)),
            timezone.make_aware(datetime.combine(day, time.max)))


def pct_change(current: Decimal, previous: Decimal) -> int | None:
    if not previous:
        return None
    return round((current - previous) * 100 / previous)


# ---------- Kunlik ko'rsatkichlar ----------

def day_flow(branch, day: date) -> dict:
    start, end = day_bounds(day)
    qs = Transaction.objects.filter(branch=branch, occurred_at__range=(start, end))
    return qs.aggregate(
        income=_dsum(F("amount") - F("commission"), direction="in", kind=Transaction.Kind.PAYMENT),
        storno=_dsum(F("amount") - F("commission"), kind=Transaction.Kind.STORNO),
        expense=_dsum(F("amount"), direction="out", kind=Transaction.Kind.EXPENSE),
        income_count=Count("id", filter=Q(direction="in", kind=Transaction.Kind.PAYMENT)),
        expense_count=Count("id", filter=Q(direction="out", kind=Transaction.Kind.EXPENSE)),
    )


# ---------- Oylik ko'rsatkichlar ----------

@dataclass
class MonthSummary:
    month: date
    expected: Decimal = ZERO
    collected_for_month: Decimal = ZERO
    received: Decimal = ZERO
    received_prev: Decimal = ZERO
    expenses: Decimal = ZERO
    payroll: Decimal = ZERO  # O'qituvchi bosqichida (oylik dvigateli) to'ldiriladi
    statuses: dict = field(default_factory=dict)

    @property
    def paid_percent(self) -> int:
        return round(self.collected_for_month * 100 / self.expected) if self.expected else 0

    @property
    def change_percent(self):
        return pct_change(self.received, self.received_prev)

    @property
    def outflow(self) -> Decimal:
        return self.expenses + self.payroll

    @property
    def outflow_ratio(self) -> float:
        return round(float(self.outflow * 100 / self.received), 1) if self.received else 0.0

    @property
    def profit(self) -> Decimal:
        return self.received - self.outflow


def _received(branch, month: date) -> Decimal:
    start, end = month_bounds(month)
    return Payment.objects.filter(branch=branch, status=Payment.Status.OK, paid_at__range=(start, end)).aggregate(
        v=_dsum(F("amount")))["v"]


def month_summary(branch, month: date) -> MonthSummary:
    today = timezone.localdate()
    month = month.replace(day=1)
    inv = Invoice.objects.filter(branch=branch, month=month, category=Invoice.Category.TUITION).exclude(
        status=Invoice.Status.CANCELLED)
    agg = inv.aggregate(
        expected=_dsum(F("amount")), collected=_dsum(F("paid")),
        paid=Count("id", filter=Q(status=Invoice.Status.PAID)),
        partial=Count("id", filter=Q(status=Invoice.Status.PARTIAL, due_date__gte=today)),
        pending=Count("id", filter=Q(status=Invoice.Status.PENDING, due_date__gte=today)),
        overdue=Count("id", filter=Q(status__in=[Invoice.Status.PENDING, Invoice.Status.PARTIAL],
                                     due_date__lt=today)),
    )
    prev = (month - timedelta(days=1)).replace(day=1)
    expenses = Expense.objects.filter(branch=branch, is_reversed=False, spent_at__year=month.year,
                                      spent_at__month=month.month).aggregate(v=_dsum(F("amount")))["v"]
    return MonthSummary(
        month=month, expected=agg["expected"], collected_for_month=agg["collected"],
        received=_received(branch, month), received_prev=_received(branch, prev), expenses=expenses,
        statuses={k: agg[k] for k in ("paid", "partial", "pending", "overdue")},
    )


# ---------- Byudjet ----------

@dataclass
class BudgetRow:
    category: ExpenseCategory
    limit: Decimal
    spent: Decimal

    @property
    def remaining(self) -> Decimal:
        return self.limit - self.spent

    @property
    def percent(self) -> int:
        return min(100, round(self.spent * 100 / self.limit)) if self.limit else (100 if self.spent else 0)

    @property
    def over(self) -> bool:
        return self.spent > self.limit


def budget(branch, month: date) -> dict:
    month = month.replace(day=1)
    limits = dict(BudgetLimit.objects.filter(branch=branch, month=month).values_list("category_id", "limit"))
    spent = dict(Expense.objects.filter(branch=branch, is_reversed=False, spent_at__year=month.year,
                                        spent_at__month=month.month)
                 .values("category_id").annotate(v=Sum("amount")).values_list("category_id", "v"))
    rows = [BudgetRow(c, limits.get(c.pk, ZERO), spent.get(c.pk, ZERO))
            for c in ExpenseCategory.objects.filter(is_active=True)]
    total_limit = sum((r.limit for r in rows), ZERO)
    total_spent = sum((r.spent for r in rows), ZERO)
    return {
        "fixed": [r for r in rows if r.category.kind == ExpenseCategory.Kind.FIXED],
        "normative": [r for r in rows if r.category.kind == ExpenseCategory.Kind.NORMATIVE],
        "limit": total_limit, "spent": total_spent, "remaining": total_limit - total_spent,
        "percent": round(total_spent * 100 / total_limit) if total_limit else 0,
    }


# ---------- O'quvchilar trendi ----------

def student_trend(branch, months: int = 6) -> list[dict]:
    today = timezone.localdate()
    cur = today.replace(day=1)
    points = []
    for _ in range(months):
        last = cur.replace(day=calendar.monthrange(cur.year, cur.month)[1])
        points.append((cur, min(last, today)))
        cur = (cur - timedelta(days=1)).replace(day=1)
    points.reverse()
    agg = Student.objects.filter(branch=branch).aggregate(**{
        f"a{i}": Count("id", filter=Q(joined_at__lte=end) & (Q(left_at__isnull=True) | Q(left_at__gt=end)))
        for i, (_, end) in enumerate(points)
    }, **{
        f"l{i}": Count("id", filter=Q(left_at__gte=start, left_at__lte=end))
        for i, (start, end) in enumerate(points)
    })
    return [{"label": MONTHS_UZ[start.month], "total": agg[f"a{i}"], "left": agg[f"l{i}"]}
            for i, (start, _) in enumerate(points)]


# ---------- Dashboard ----------

def reception_dashboard(branch, month: date | None = None) -> dict:
    today = timezone.localdate()
    month = (month or today).replace(day=1)
    month_start = today.replace(day=1)
    students = Student.objects.filter(branch=branch).aggregate(
        active=Count("id", filter=Q(status=Student.Status.ACTIVE)),
        new=Count("id", filter=Q(joined_at__gte=month_start, status=Student.Status.ACTIVE)))
    teachers = Teacher.objects.filter(branch=branch).exclude(status__in=Teacher.NOT_WORKING).aggregate(
        total=Count("id"), vacation=Count("id", filter=Q(status=Teacher.Status.VACATION)))
    today_flow = day_flow(branch, today)
    yesterday_flow = day_flow(branch, today - timedelta(days=1))
    return {
        "today": today, "month": month, "month_label": f"{MONTHS_UZ_FULL[month.month]} {month.year}",
        "students": students, "teachers": teachers,
        "today_flow": today_flow,
        "income_change": pct_change(today_flow["income"], yesterday_flow["income"]),
        "cash_balance": ledger.balance(ledger.get_account(branch, Account.Kind.CASH)),
        "summary": month_summary(branch, month),
        "budget": budget(branch, month),
        "trend": student_trend(branch),
    }


def budget_months(branch, count: int = 6) -> list[tuple[str, str]]:
    today = timezone.localdate().replace(day=1)
    result, cur = [], today
    for _ in range(count):
        result.append((cur.strftime("%Y-%m"), f"{MONTHS_UZ_FULL[cur.month]} {cur.year}"))
        cur = (cur - timedelta(days=1)).replace(day=1)
    return result


def student_finance(student) -> dict:
    """O'quvchi kartasi → To'lov. Grafik oyma-oy yaratiladi: jadvalda faqat yaratilgan (hisoblangan) oylar."""
    invoices = list(student.invoices.exclude(status=Invoice.Status.CANCELLED)
                    .filter(category=Invoice.Category.TUITION).select_related("contract").order_by("month"))
    today = timezone.localdate()
    contract = (student.contracts.filter(status="signed").select_related("academic_year")
                .order_by("-start_date").first())
    created = {i.month for i in invoices}
    missing = [m for m in invoices_service.month_starts(contract.start_date, contract.end_date)
               if m not in created] if contract else []
    return {
        "invoices": invoices,
        "charged": sum((i.amount for i in invoices), ZERO),
        "paid_total": sum((i.paid for i in invoices), ZERO),
        "debt": sum((i.remaining for i in invoices), ZERO),
        "overdue": sum((i.remaining for i in invoices if i.due_date < today), ZERO),
        "schedule_contract": contract,
        "missing_months": missing,  # hali yaratilmagan oylar ("Grafik" oynasi uchun)
        "payments": student.payments.select_related("received_by").order_by("-paid_at")[:20],
        "finance_visible": True,
    }


def guardian_finance(student_ids: list[int]) -> dict:
    """Ota-ona kartasi: barcha farzandlarining qarzi, to'langani, qarzdor oylari va to'lovlari (Reception)."""
    invoices = list(Invoice.objects.filter(student_id__in=student_ids, category=Invoice.Category.TUITION)
                    .exclude(status=Invoice.Status.CANCELLED).select_related("student__branch", "contract")
                    .order_by("month", "student__last_name"))
    per_student = {sid: {"debt": ZERO, "paid": ZERO} for sid in student_ids}
    for i in invoices:
        per_student[i.student_id]["debt"] += i.remaining
        per_student[i.student_id]["paid"] += i.paid
    return {
        "per_student": per_student,
        "total_debt": sum((v["debt"] for v in per_student.values()), ZERO),
        "total_paid": sum((v["paid"] for v in per_student.values()), ZERO),
        "invoices": invoices,  # "Qarzdorliklar (grafiklar)" — asl tizimdagidek barcha oylar, holati bilan
        "debt_count": sum(1 for i in invoices if i.remaining > 0),
        "payments": list(Payment.objects.filter(student_id__in=student_ids)
                         .select_related("student", "received_by")
                         .prefetch_related(Prefetch("transactions", to_attr="payment_trx",
                                                    queryset=Transaction.objects.filter(kind=Transaction.Kind.PAYMENT)))
                         .order_by("-paid_at")[:100]),
    }


# ---------- Kassa paneli ----------

ACCOUNT_LABELS = {Account.Kind.CASH: ("Naqd", "cash"), Account.Kind.TERMINAL: ("Terminal", "card"),
                  Account.Kind.BANK: ("Bank o'tkazmasi", "bank")}


def _flow(qs) -> dict:
    """Kirim (net — komissiyasiz) va chiqim; soni bilan."""
    return qs.aggregate(
        income=_dsum(F("amount") - F("commission"), direction="in"),
        outcome=_dsum(F("amount") - F("commission"), direction="out"),
        income_count=Count("id", filter=Q(direction="in")),
        outcome_count=Count("id", filter=Q(direction="out")),
    )


def cashbox_overview(branch, day: date) -> dict:
    """Kirim → Kassa paneli. Hamma raqam `Transaction` jurnalidan (qoldiq hech qayerda saqlanmaydi)."""
    accounts = {kind: ledger.get_account(branch, kind) for kind in ACCOUNT_LABELS}
    day_start, day_end = day_bounds(day)
    month_start, _ = month_bounds(day)
    cash_balance = ledger.balance(accounts[Account.Kind.CASH], until=day_end)
    bank_balance = (ledger.balance(accounts[Account.Kind.BANK], until=day_end)
                    + ledger.balance(accounts[Account.Kind.TERMINAL], until=day_end))

    txs = Transaction.objects.filter(branch=branch)
    today, month = _flow(txs.filter(occurred_at__range=(day_start, day_end))), \
        _flow(txs.filter(occurred_at__range=(month_start, day_end)))
    by_kind = []
    for kind, (label, code) in ACCOUNT_LABELS.items():
        f = _flow(txs.filter(account=accounts[kind], occurred_at__range=(day_start, day_end)))
        if f["income_count"] or f["outcome_count"] or kind == Account.Kind.CASH:
            by_kind.append({"label": label, "code": code, **f, "net": f["income"] - f["outcome"]})
    cash_today = next(k for k in by_kind if k["code"] == "cash")

    session = CashSession.objects.filter(branch=branch, closed_at__isnull=True).select_related("opened_by").first()
    last_move = None
    if session:
        last_move = (txs.filter(account=accounts[Account.Kind.CASH], occurred_at__gte=session.opened_at)
                     .order_by("-occurred_at").values_list("occurred_at", flat=True).first())
    net = today["income"] - today["outcome"]
    return {
        "day": day, "cash_balance": cash_balance, "bank_balance": bank_balance,
        "total_balance": cash_balance + bank_balance,
        "today": today, "month": month, "net": net, "month_net": month["income"] - month["outcome"],
        "ratio": round(today["outcome"] * 100 / today["income"]) if today["income"] else 0,
        "cash_today": cash_today, "by_kind": by_kind,
        "session": session, "last_move": last_move, "stable": net >= 0,
    }


# ---------- To'lovlar ro'yxati ----------

@dataclass(frozen=True)
class PaymentFilters:
    q: str = ""
    date_from: date | None = None
    date_to: date | None = None
    method: str = ""
    school_class: int | None = None
    received_by: int | None = None


def payments_list(branch, f: PaymentFilters):
    qs = (Payment.objects.filter(branch=branch)
          .select_related("student__school_class", "received_by", "account"))
    if f.date_from:
        qs = qs.filter(paid_at__gte=day_bounds(f.date_from)[0])
    if f.date_to:
        qs = qs.filter(paid_at__lte=day_bounds(f.date_to)[1])
    if f.method:
        qs = qs.filter(method=f.method)
    if f.school_class:
        qs = qs.filter(student__school_class_id=f.school_class)
    if f.received_by:
        qs = qs.filter(received_by_id=f.received_by)
    for term in f.q.split()[:5]:  # ism, familiya, o'quvchi kodi, kvitansiya raqami yoki izoh
        qs = qs.filter(Q(student__last_name__icontains=term) | Q(student__first_name__icontains=term)
                       | Q(student__code__icontains=term) | Q(number__icontains=term) | Q(note__icontains=term))
    return qs.order_by("-paid_at")


def payments_stats(branch, qs, f: PaymentFilters) -> dict:
    stats = qs.aggregate(total=_dsum("amount", status=Payment.Status.OK),
                         count=Count("id", filter=Q(status=Payment.Status.OK)),
                         storno_count=Count("id", filter=Q(status=Payment.Status.REVERSED)))
    refunds = Transaction.objects.filter(branch=branch, kind=Transaction.Kind.REFUND)
    if f.date_from:
        refunds = refunds.filter(occurred_at__gte=day_bounds(f.date_from)[0])
    if f.date_to:
        refunds = refunds.filter(occurred_at__lte=day_bounds(f.date_to)[1])
    stats["refunded"] = refunds.aggregate(v=_dsum("amount"))["v"]  # o'qishdan chiqqanda qaytarilgan
    return stats


def payment_receivers(branch):
    """"Yaratuvchi" filtri: shu filialda to'lov qabul qilgan xodimlar."""
    from apps.accounts.models import User
    return User.objects.filter(pk__in=Payment.objects.filter(branch=branch).values("received_by")) \
        .order_by("last_name", "first_name")


# ---------- Tranzaksiyalar ro'yxati ----------

# Kategoriyalar: to'lovlar turi bo'yicha ajratiladi (o'qish / yotoqxona), qolganlari — jurnal turi.
# O'qituvchi/xodim maoshi — oylik moduli (4T) bilan qo'shiladi.
TRANSACTION_CATEGORIES = [
    ("tuition", "O'quvchi to'lovi"), ("dorm", "Yotoqxona to'lovi"), ("expense", "Xarajat"),
    ("refund", "Qaytarilgan to'lov"), ("storno", "Storno"), ("adjustment", "Kassa tafovuti"),
    ("transfer", "Ichki o'tkazma"),
]
_CATEGORY_Q = {
    "tuition": Q(kind=Transaction.Kind.PAYMENT, payment__category=Invoice.Category.TUITION),
    "dorm": Q(kind=Transaction.Kind.PAYMENT, payment__category=Invoice.Category.DORM),
    "expense": Q(kind=Transaction.Kind.EXPENSE), "refund": Q(kind=Transaction.Kind.REFUND),
    "storno": Q(kind=Transaction.Kind.STORNO), "adjustment": Q(kind=Transaction.Kind.ADJUSTMENT),
    "transfer": Q(kind=Transaction.Kind.TRANSFER),
}


@dataclass(frozen=True)
class TransactionFilters:
    q: str = ""
    direction: str = ""
    categories: tuple[str, ...] = ()
    account_kinds: tuple[str, ...] = ()
    card_network: str = ""
    status: str = ""  # "ok" | "cancelled" (storno qilingan to'lov) | "storno" (teskari yozuv)
    created_by: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    min_amount: Decimal | None = None


def transactions_list(branch, f: TransactionFilters):
    qs = (Transaction.objects.filter(branch=branch)
          .select_related("account", "created_by", "branch", "payment__student", "expense__category"))
    if f.date_from:
        qs = qs.filter(occurred_at__gte=day_bounds(f.date_from)[0])
    if f.date_to:
        qs = qs.filter(occurred_at__lte=day_bounds(f.date_to)[1])
    for lookup, value in (("direction", f.direction), ("payment__card_network", f.card_network),
                          ("created_by_id", f.created_by)):
        if value:
            qs = qs.filter(**{lookup: value})
    if f.account_kinds:
        qs = qs.filter(account__kind__in=f.account_kinds)
    if f.categories:
        cond = Q()
        for c in f.categories:
            cond |= _CATEGORY_Q.get(c, Q(pk__in=[]))
        qs = qs.filter(cond)
    cancelled_q = Q(kind=Transaction.Kind.PAYMENT, payment__status=Payment.Status.REVERSED)
    storno_q = Q(kind=Transaction.Kind.STORNO)
    if f.status == "cancelled":
        qs = qs.filter(cancelled_q)
    elif f.status == "storno":
        qs = qs.filter(storno_q)
    elif f.status == "ok":
        qs = qs.exclude(cancelled_q | storno_q)
    if f.min_amount:
        qs = qs.filter(amount__gte=f.min_amount)
    q = f.q.strip()
    if q:
        cond = Q(description__icontains=q) | Q(payment__number__icontains=q)
        digits = q.upper().removeprefix("TRX-")
        if digits.isdigit():
            cond |= Q(pk=int(digits))
        qs = qs.filter(cond)
    return qs.order_by("-occurred_at", "-pk")


def transactions_stats(qs) -> dict:
    s = qs.aggregate(income=_dsum("amount", direction="in"), outcome=_dsum("amount", direction="out"),
                     commission=_dsum("commission", direction="in"), count=Count("id"))
    s["net"] = s["income"] - s["commission"] - s["outcome"]
    by_kind = []
    for kind, (label, _) in ACCOUNT_LABELS.items():
        k = qs.filter(account__kind=kind).aggregate(
            income=_dsum("amount", direction="in"), outcome=_dsum("amount", direction="out"),
            commission=_dsum("commission", direction="in"), count=Count("id"))
        if k["count"]:
            pct = settings.TERMINAL_COMMISSION_PERCENT if kind == Account.Kind.TERMINAL else 0
            by_kind.append({"label": label, "kind": kind, "percent": pct, **k,
                            "net": k["income"] - k["commission"] - k["outcome"]})
    s["by_kind"] = by_kind
    return s


def transaction_creators(branch):
    from apps.accounts.models import User
    return User.objects.filter(pk__in=Transaction.objects.filter(branch=branch).values("created_by")) \
        .order_by("last_name", "first_name")


# ---------- Bank hisobi ----------

def bank_overview(branch, date_from: date, date_to: date) -> dict:
    """Kirim → Bank hisobi: bank o'tkazmalari, terminal (komissiyasiz — net) va ichki o'tkazmalar davr bo'yicha."""
    start, end = day_bounds(date_from)[0], day_bounds(date_to)[1]
    kinds = (Account.Kind.BANK, Account.Kind.TERMINAL)
    txs = (Transaction.objects.filter(branch=branch, account__kind__in=kinds, occurred_at__range=(start, end))
           .select_related("account", "payment"))

    def flow(qs):
        return qs.aggregate(income=_dsum("amount", direction="in"), outcome=_dsum("amount", direction="out"),
                            commission=_dsum("commission"), count=Count("id"))

    not_transfer = ~Q(kind=Transaction.Kind.TRANSFER)
    bank = flow(txs.filter(not_transfer, account__kind=Account.Kind.BANK))
    terminal = flow(txs.filter(not_transfer, account__kind=Account.Kind.TERMINAL))
    transfers = flow(txs.filter(kind=Transaction.Kind.TRANSFER))
    bank["net"] = bank["income"] - bank["outcome"] - bank["commission"]
    terminal["net"] = terminal["income"] - terminal["outcome"] - terminal["commission"]
    transfers["net"] = transfers["income"] - transfers["outcome"]
    total = bank["net"] + terminal["net"] + transfers["net"]
    all_time = sum((ledger.balance(ledger.get_account(branch, k)) for k in kinds), ZERO)
    return {"bank": bank, "terminal": terminal, "transfers": transfers, "total": total, "all_time": all_time,
            "stable": total >= 0, "transactions": txs.order_by("-occurred_at", "-pk")}


# ---------- To'lov grafiklari (barcha o'quvchilar oylari) ----------

@dataclass(frozen=True)
class InvoiceFilters:
    q: str = ""
    school_class: int | None = None
    academic_year: int | None = None
    month: date | None = None
    state: str = ""  # pending | partial | paid | overdue | waived | cancelled
    student_status: str = ""
    category: str = Invoice.Category.TUITION


def _academic_year_q(f: InvoiceFilters, prefix: str = "") -> Q:
    """O'qish — shartnomaning o'quv yili; yotoqxonada shartnoma yo'q — o'quv yili oylari oralig'i."""
    if f.category == Invoice.Category.TUITION:
        return Q(**{f"{prefix}contract__academic_year_id": f.academic_year})
    year = AcademicYear.objects.filter(pk=f.academic_year).first()
    if not year:
        return Q()
    return Q(**{f"{prefix}month__gte": year.start_date.replace(day=1), f"{prefix}month__lte": year.end_date})


def invoices_list(branch, f: InvoiceFilters):
    """O'qish to'lovi grafiklari. "Jami" = oylik (chegirmadan keyin, kechilgandan oldin).

    Bekor qilingan oylar faqat "Bekor qilingan" holati tanlanganda ko'rinadi (statistikaga aralashmasin).
    """
    today = timezone.localdate()
    qs = (Invoice.objects.filter(branch=branch, category=f.category)
          .select_related("student__school_class", "contract", "dorm_stay__room"))
    if f.state == "cancelled":
        qs = qs.filter(status=Invoice.Status.CANCELLED)
    else:
        qs = qs.exclude(status=Invoice.Status.CANCELLED)
    if f.school_class:
        qs = qs.filter(student__school_class_id=f.school_class)
    if f.academic_year:
        qs = qs.filter(_academic_year_q(f))
    if f.month:
        qs = qs.filter(month=f.month.replace(day=1))
    if f.student_status:
        qs = qs.filter(student__status=f.student_status)
    unpaid = Q(status__in=[Invoice.Status.PENDING, Invoice.Status.PARTIAL])
    if f.state == "overdue":
        qs = qs.filter(unpaid, due_date__lt=today)
    elif f.state == "paid":
        qs = qs.filter(status=Invoice.Status.PAID)
    elif f.state in ("partial", "pending"):
        qs = qs.filter(status=f.state, due_date__gte=today)
    elif f.state == "waived":  # kechilgan qismi bor (oy o'rtasida kelgan/chiqqan, imtiyoz)
        qs = qs.filter(waived__gt=0)
    for term in f.q.split()[:5]:
        qs = qs.filter(Q(student__last_name__icontains=term) | Q(student__first_name__icontains=term)
                       | Q(student__middle_name__icontains=term) | Q(student__code__icontains=term))
    return qs.order_by("-month", "student__last_name", "student__first_name")


def invoices_stats(qs) -> dict:
    s = qs.aggregate(amount=_dsum("amount"), discount=_dsum("discount"), waived=_dsum("waived"),
                     paid=_dsum("paid"), count=Count("id"))
    s["total"] = s["amount"] + s["waived"]  # jami hisoblangan (kechilgandan oldin)
    s["remaining"] = s["amount"] - s["paid"]
    return s


# ---------- Qarzdorlar ----------

def debtors(branch, f: InvoiceFilters):
    """Qarzdor o'quvchilar (har biri bitta qator) — `f.category` bo'yicha (o'qish yoki yotoqxona).
    Faqat kelgan oylar (joriy oygacha) — oldindan yaratilgan kelajak oylar qarz emas.
    Tartib: qoldiq kamayishi bo'yicha."""
    today = timezone.localdate()
    inv = (Q(invoices__category=f.category) & ~Q(invoices__status=Invoice.Status.CANCELLED)
           & Q(invoices__month__lte=today.replace(day=1)))
    if f.academic_year:
        inv &= _academic_year_q(f, "invoices__")
    if f.month:
        inv &= Q(invoices__month=f.month.replace(day=1))
    unpaid = inv & Q(invoices__paid__lt=F("invoices__amount"))
    last_payment = (Payment.objects.filter(student=OuterRef("pk"), category=f.category, status=Payment.Status.OK)
                    .order_by("-paid_at"))
    qs = (Student.objects.filter(branch=branch).select_related("school_class")
          .annotate(total=Coalesce(Sum("invoices__amount", filter=inv), ZERO, output_field=DecimalField()),
                    paid_sum=Coalesce(Sum("invoices__paid", filter=inv), ZERO, output_field=DecimalField()),
                    discount_sum=Coalesce(Sum("invoices__discount", filter=inv), ZERO, output_field=DecimalField()),
                    debt_months=Count("invoices", filter=unpaid),
                    overdue_months=Count("invoices", filter=unpaid & Q(invoices__due_date__lt=today)),
                    partial_months=Count("invoices", filter=inv & Q(invoices__status=Invoice.Status.PARTIAL)),
                    last_amount=Subquery(last_payment.values("amount")[:1]),
                    last_paid_at=Subquery(last_payment.values("paid_at")[:1]))
          .annotate(remaining=F("total") - F("paid_sum")).filter(remaining__gt=0))
    if f.school_class:
        qs = qs.filter(school_class_id=f.school_class)
    if f.student_status:
        qs = qs.filter(status=f.student_status)
    if f.state == "overdue":
        qs = qs.filter(overdue_months__gt=0)
    elif f.state == "partial":
        qs = qs.filter(partial_months__gt=0)
    elif f.state == "pending":
        qs = qs.filter(overdue_months=0)
    for term in f.q.split()[:5]:
        qs = qs.filter(Q(last_name__icontains=term) | Q(first_name__icontains=term)
                       | Q(middle_name__icontains=term) | Q(code__icontains=term))
    return qs.order_by("-remaining", "last_name")


def debtors_stats(branch, f: InvoiceFilters, debtors_qs) -> dict:
    """Kartalar: shu filtr bo'yicha kelgan oylar grafiklari yig'indisi + qarzdor o'quvchilar soni."""
    today = timezone.localdate()
    qs = invoices_list(branch, InvoiceFilters(school_class=f.school_class, academic_year=f.academic_year,
                                              month=f.month, student_status=f.student_status, q=f.q,
                                              category=f.category))
    s = invoices_stats(qs.filter(month__lte=today.replace(day=1)))
    s["students"] = debtors_qs.count()
    return s


def student_debt_card(student, category=Invoice.Category.TUITION) -> dict:
    """Qarzdorlar yon paneli (ma'lumot / to'lov): kelgan oylar bo'yicha qisqa xulosa."""
    current = timezone.localdate().replace(day=1)
    invoices = list(student.invoices.filter(category=category, month__lte=current)
                    .exclude(status=Invoice.Status.CANCELLED).select_related("contract", "dorm_stay__room")
                    .order_by("month"))
    unpaid = [i for i in invoices if i.remaining > 0]
    last_payment = (student.payments.filter(category=category, status=Payment.Status.OK)
                    .order_by("-paid_at").first())
    return {
        "invoices": invoices, "unpaid": unpaid, "last_payment": last_payment,
        "total": sum((i.amount for i in invoices), ZERO), "discount": sum((i.discount for i in invoices), ZERO),
        "paid": sum((i.paid for i in invoices), ZERO), "remaining": sum((i.remaining for i in invoices), ZERO),
    }
