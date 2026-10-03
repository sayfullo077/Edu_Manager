"""Direktor paneli: boshqa ilovalar ma'lumotidan jamlangan ko'rsatkichlar (faqat o'qish, o'z modeli yo'q)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.academics.models import ClassAttendance, SchoolClass
from apps.accounts.models import Role, UserRole
from apps.contracts.models import Contract
from apps.dorm import selectors as dorm_selectors
from apps.dorm.models import DormAttendance, DormStay
from apps.finance import selectors as finance_selectors
from apps.finance.models import Account, Expense, ExpenseCategory, Invoice, Payment
from apps.finance.services import ledger
from apps.payroll.models import SalaryPayment
from apps.payroll.selectors import month_payroll
from apps.people.models import Student, Teacher

ZERO = Decimal("0")
ACTIVE = Student.Status.ACTIVE


def _prev_month(month: date) -> date:
    return (month - timedelta(days=1)).replace(day=1)


def months_back(month: date, count: int) -> list[date]:
    out = [month]
    for _ in range(count - 1):
        out.append(_prev_month(out[-1]))
    return list(reversed(out))


def debt_total(branch, today: date) -> dict:
    """Muddati o'tgan qarz (o'qish + yotoqxona): summa va qarzdor o'quvchilar soni."""
    qs = Invoice.objects.filter(branch=branch, due_date__lt=today,
                                status__in=[Invoice.Status.PENDING, Invoice.Status.PARTIAL])
    agg = qs.aggregate(total=Sum(F("amount") - F("paid")), students=Count("student", distinct=True))
    return {"total": agg["total"] or ZERO, "students": agg["students"]}


def attendance_today(branch, today: date) -> dict:
    """Bugungi sinf davomati: belgilangan sinflar, keldi/kelmadi va foiz."""
    classes = SchoolClass.objects.filter(branch=branch, is_active=True, academic_year__is_current=True)
    marks = ClassAttendance.objects.filter(school_class__in=classes, date=today)
    agg = marks.aggregate(
        total=Count("id"), came=Count("id", filter=Q(status__in=["B", "K"])),
        absent=Count("id", filter=Q(status="Y")), excused=Count("id", filter=Q(status="S")),
        classes=Count("school_class", distinct=True))
    agg["all_classes"] = classes.count()
    agg["percent"] = round(agg["came"] * 100 / agg["total"]) if agg["total"] else None
    return agg


def money_trend(branch, month: date, count: int = 6) -> list[dict]:
    """Oylar bo'yicha kirim (to'lovlar) va chiqim (xarajatlar, oylik ham) — bitta shkalada.

    2 ta guruhlangan so'rov (oyiga alohida so'rov emas) — 12 oylik hisobotda ham tez.
    """
    months = months_back(month, count)
    start, _ = finance_selectors.month_bounds(months[0])
    _, end = finance_selectors.month_bounds(months[-1])
    tz = timezone.get_current_timezone()
    income = {row["m"].date() if hasattr(row["m"], "date") else row["m"]: row["v"] for row in (
        Payment.objects.filter(branch=branch, status=Payment.Status.OK, paid_at__range=(start, end))
        .annotate(m=TruncMonth("paid_at", tzinfo=tz)).values("m").annotate(v=Sum("amount")))}
    expense = {row["m"]: row["v"] for row in (
        Expense.objects.filter(branch=branch, is_reversed=False, spent_at__gte=months[0],
                               spent_at__lte=end.date())
        .annotate(m=TruncMonth("spent_at")).values("m").annotate(v=Sum("amount")))}
    rows = []
    for m in months:
        inc, exp = income.get(m, ZERO), expense.get(m, ZERO)
        rows.append({"month": m, "label": f"{finance_selectors.MONTHS_UZ_FULL[m.month]}", "income": inc,
                     "expense": exp, "net": inc - exp})
    top = max([max(r["income"], r["expense"]) for r in rows] + [Decimal("1")])
    for r in rows:
        r["income_pct"] = round(r["income"] * 100 / top)
        r["expense_pct"] = round(r["expense"] * 100 / top)
    return rows


def dashboard(branch, today: date) -> dict:
    month = today.replace(day=1)
    month_start = month
    students = Student.objects.filter(branch=branch).aggregate(
        active=Count("id", filter=Q(status=ACTIVE)),
        new=Count("id", filter=Q(status=ACTIVE, joined_at__gte=month_start)),
        left=Count("id", filter=Q(left_at__gte=month_start)))
    contracts = Contract.objects.filter(branch=branch).aggregate(
        signed=Count("id", filter=Q(status=Contract.Status.SIGNED)),
        pending=Count("id", filter=Q(status__in=[Contract.Status.DRAFT, Contract.Status.SENT])))
    teachers = Teacher.objects.filter(branch=branch).exclude(status__in=Teacher.NOT_WORKING).aggregate(
        total=Count("id"), vacation=Count("id", filter=Q(status=Teacher.Status.VACATION)))
    summary = finance_selectors.month_summary(branch, month)
    payroll = month_payroll(branch, month)
    paid_salary = SalaryPayment.objects.filter(branch=branch, month=month).aggregate(v=Sum("amount"))["v"] or ZERO
    balances = {kind: ledger.balance(ledger.get_account(branch, kind)) for kind in Account.Kind.values}
    trend = money_trend(branch, month)
    return {
        "today": today, "month": month,
        "month_label": f"{finance_selectors.MONTHS_UZ_FULL[month.month]} {month.year}",
        "students": students, "contracts": contracts, "teachers": teachers,
        "summary": summary, "debt": debt_total(branch, today),
        "payroll": {"real": payroll.totals["total"].real, "max": payroll.totals["total"].max,
                    "paid": paid_salary, "teachers": len(payroll.rows)},
        "balances": balances, "balance_total": sum(balances.values(), ZERO),
        "budget": finance_selectors.budget(branch, month),
        "attendance": attendance_today(branch, today),
        "dorm": dorm_selectors.occupancy(branch),
        "dorm_today": dorm_selectors.attendance_today(branch, today),
        "money_trend": trend, "net_month": trend[-1]["net"],
        "student_trend": finance_selectors.student_trend(branch),
    }


# ---------- Moliyaviy hisobot ----------

def finance_report(branch, month: date) -> dict:
    """Oy bo'yicha kirim (turlari), chiqim (kategoriyalar) va sof natija; 12 oylik jadval."""
    start, end = finance_selectors.month_bounds(month)
    pay = Payment.objects.filter(branch=branch, status=Payment.Status.OK, paid_at__range=(start, end))
    income = {row["category"]: row["v"] for row in pay.values("category").annotate(v=Sum("amount"))}
    income_rows = [{"label": label, "value": income.get(value, ZERO)} for value, label in Invoice.Category.choices]
    exp = (Expense.objects.filter(branch=branch, is_reversed=False, spent_at__year=month.year,
                                  spent_at__month=month.month)
           .values("category").annotate(v=Sum("amount")))
    spent = {row["category"]: row["v"] for row in exp}
    expense_rows = sorted(({"label": c.name, "value": spent[c.pk]} for c in ExpenseCategory.objects.filter(
        pk__in=spent.keys())), key=lambda r: -r["value"])
    income_total = sum((r["value"] for r in income_rows), ZERO)
    expense_total = sum((r["value"] for r in expense_rows), ZERO)
    for rows, total in ((income_rows, income_total), (expense_rows, expense_total)):
        for r in rows:
            r["pct"] = round(r["value"] * 100 / total) if total else 0
    summary = finance_selectors.month_summary(branch, month)
    return {
        "month": month, "income_rows": income_rows, "expense_rows": expense_rows,
        "income": income_total, "expense": expense_total, "net": income_total - expense_total,
        "summary": summary, "year": money_trend(branch, month, 12),
    }


# ---------- Davomat hisoboti ----------

def attendance_report(branch, day: date) -> dict:
    """Sinflar kesimida kunlik davomat (sinf rahbari kiritgani) + yotoqxona."""
    classes = list(SchoolClass.objects.filter(branch=branch, is_active=True, academic_year__is_current=True)
                   .select_related("homeroom_teacher__user").order_by("kind", "grade", "name"))
    counts = {c["school_class"]: c for c in ClassAttendance.objects.filter(school_class__in=classes, date=day)
              .values("school_class").annotate(
                  total=Count("id"), came=Count("id", filter=Q(status="B")), late=Count("id", filter=Q(status="K")),
                  absent=Count("id", filter=Q(status="Y")), excused=Count("id", filter=Q(status="S")))}
    sizes = dict(Student.objects.filter(school_class__in=classes, status=ACTIVE).values("school_class")
                 .annotate(n=Count("id")).values_list("school_class", "n"))
    rows, tot = [], {"students": 0, "total": 0, "came": 0, "late": 0, "absent": 0, "excused": 0}
    for c in classes:
        r = counts.get(c.pk, {"total": 0, "came": 0, "late": 0, "absent": 0, "excused": 0})
        n = sizes.get(c.pk, 0)
        row = {"c": c, "students": n, **{k: r[k] for k in ("total", "came", "late", "absent", "excused")}}
        row["percent"] = round((row["came"] + row["late"]) * 100 / row["total"]) if row["total"] else None
        row["state"] = "none" if not row["total"] else "full" if row["total"] >= n else "partial"
        rows.append(row)
        tot["students"] += n
        for k in ("total", "came", "late", "absent", "excused"):
            tot[k] += row[k]
    tot["percent"] = round((tot["came"] + tot["late"]) * 100 / tot["total"]) if tot["total"] else None
    dorm_stays = DormStay.objects.filter(room__branch=branch, checked_in__lte=day).filter(
        Q(checked_out__isnull=True) | Q(checked_out__gte=day))
    dorm = DormAttendance.objects.filter(stay__in=dorm_stays, date=day).aggregate(
        present=Count("id", filter=Q(status__in=["B", "K"])), absent=Count("id", filter=Q(status__in=["Y", "S"])),
        marked=Count("id"))
    dorm["residents"] = dorm_stays.count()
    dorm["unmarked"] = max(dorm["residents"] - dorm["marked"], 0)
    return {"day": day, "rows": rows, "total": tot, "dorm": dorm,
            "not_marked": [r for r in rows if r["state"] == "none" and r["students"]]}


# ---------- Xodimlar ----------

STAFF_ROLES = (Role.RECEPTION, Role.HEAD_TEACHER, Role.TEACHER)  # direktor boshqaradigan rollar


def staff(branch) -> list[dict]:
    """Filial xodimlari: foydalanuvchi va uning shu filialdagi rollari (faol/o'chirilgan)."""
    roles = (UserRole.objects.filter(branch=branch).select_related("user").order_by("user__last_name",
                                                                                     "user__first_name", "role"))
    people: dict[int, dict] = {}
    for r in roles:
        p = people.setdefault(r.user_id, {"user": r.user, "roles": []})
        r.manageable = r.role in STAFF_ROLES
        p["roles"].append(r)
    result = list(people.values())
    for p in result:
        p["active"] = any(r.is_active for r in p["roles"])
    return result


def staff_stats(people: list[dict]) -> dict:
    counts = {code: 0 for code, _ in Role.choices}
    for p in people:
        for r in p["roles"]:
            if r.is_active:
                counts[r.role] += 1
    return {"total": len(people), "active": sum(1 for p in people if p["active"]), **counts}

