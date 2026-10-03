from datetime import date, time
from decimal import Decimal as D

import pytest
from django.urls import reverse

from apps.academics.models import Group, GroupMembership, GroupSubject, Lesson, SchoolClass, Subject, TimeSlot
from apps.accounts.models import Role, User
from apps.finance.models import Invoice
from apps.payroll.domain.calc import Homeroom, Line, Pair, Rates, StudentShare, TeacherPay
from apps.payroll.models import Penalty
from apps.payroll.selectors import month_payroll, payroll_settings
from apps.people.models import Certificate, Student, Teacher
from conftest import make_staff

SEP = date(2026, 9, 1)


# ---------------- Sof hisob (domain) ----------------

def share(sid, paid, amount="1750000", full="1750000"):
    return StudentShare(sid, f"O'quvchi {sid}", D(paid), D(amount), D(full))


def test_line_per_lesson_and_per_student():
    lesson_line = Line(1, "4-A", "4-A", 1, "Matematika", True, D("2400"), D("0"), 4, False,
                       [share(1, "1750000"), share(2, "875000")])
    # 4 dars × 2400 × (1 + 0.5) ; max — ikkalasi to'liq
    assert lesson_line.gross == Pair(D("14400"), D("19200")) and not lesson_line.deduction
    group_line = Line(2, "Aniq-01", "Aniq1", 2, "IT", False, D("120000"), D("15"), 8, False,
                      [share(3, "1850000", "1850000", "1850000")])
    assert group_line.gross == Pair(D("120000"), D("120000"))
    assert group_line.deduction == Pair(D("18000"), D("18000"))


def test_discount_reduces_teacher_share():
    # Chegirmali o'quvchi: to'lashi kerak 1 400 000, tarif 1 750 000 → max ulush 0.8
    line = Line(1, "g", "4-A", 1, "Fan", False, D("120000"), D("0"), 0, False, [share(1, "700000", "1400000")])
    assert line.gross == Pair(D("48000"), D("96000"))


def test_teacher_bonuses_and_total():
    math = Line(1, "4-A", "4-A", 10, "Matematika", True, D("2400"), D("0"), 10, False, [share(1, "1750000")])
    rus = Line(2, "5-R", "5-R", 11, "Rus tili", True, D("2400"), D("0"), 5, True, [share(2, "1750000")])
    it = Line(3, "Aniq", "Aniq1", 12, "IT", False, D("100000"), D("15"), 0, False, [share(3, "1750000")])
    pay = TeacherPay(1, Rates(D("10"), D("30"), D("15"), D("30000")), [math, rus, it],
                     fixed_salary=D("500000"), cert_subjects=frozenset({12}),
                     homerooms=[Homeroom("4-A", [share(1, "1750000"), share(4, "700000", "1400000")])],
                     penalties=D("5000"))
    assert pay.base.real == D("24000") + D("12000") + D("100000") + D("500000")
    assert pay.category_bonus.real == D("3600")       # 10% × darsbay (24 000 + 12 000)
    assert pay.certificate_bonus.real == D("30000")   # 30% × IT qismi
    assert pay.language_bonus.real == D("1800")       # 15% × rus sinfi qismi
    # o'quvchi boshiga 30 000 × ulush: (1 + 0.4) real, (1 + 0.8) max
    assert pay.homeroom_bonus == Pair(D("42000"), D("54000")) and pay.homeroom_students == 2
    assert pay.deductions.real == D("15000") + D("5000")  # 15% ushlanma + qo'lda jarima
    assert pay.total.real == D("636000") + D("3600") + D("30000") + D("1800") + D("42000") - D("20000")
    assert (pay.subjects_count, pay.lessons, pay.students_count) == (3, 15, 3)
    # Qator summasi = asosiy + o'sha qatorga tegishli ustama − ushlanma; qatorlar + S/R + belgilangan − jarima = jami
    totals = {i["line"].subject_id: i["total"].real for i in pay.items}
    assert totals == {10: D("26400"), 11: D("15000"), 12: D("115000")}
    assert sum(totals.values()) + D("42000") + D("500000") - D("5000") == pay.total.real
    assert pay.gap == pay.total.real - pay.total.max


def test_certificate_without_subject_covers_all():
    a = Line(1, "g", "c", 1, "A", True, D("1000"), D("0"), 1, False, [share(1, "1750000")])
    b = Line(2, "g", "c", 2, "B", True, D("1000"), D("0"), 1, False, [share(2, "1750000")])
    pay = TeacherPay(1, Rates(certificate_percent=D("30")), [a, b], cert_all_subjects=True)
    assert pay.certificate_bonus.real == D("600")


# ---------------- Bazadan hisob ----------------

@pytest.fixture
def head_client(client, branch):
    client.force_login(make_staff(branch, Role.HEAD_TEACHER, "998900000190"))
    return client


def make_teacher(branch, phone, last, **kw):
    user = User.objects.create_user(phone, "Str0ng-pass-123", last_name=last, first_name="Test")
    return Teacher.objects.create(user=user, branch=branch, **kw)


def student(branch, name, school_class=None):
    return Student.objects.create(branch=branch, last_name="Test", first_name=name, birth_date=date(2016, 1, 1),
                                  gender="M", grade=4, joined_at=date(2026, 9, 2), school_class=school_class)


def invoice(branch, s, paid, amount="1750000", full="1750000", month=SEP):
    status = Invoice.Status.PAID if D(paid) >= D(amount) else Invoice.Status.PARTIAL if D(paid) else \
        Invoice.Status.PENDING
    return Invoice.objects.create(branch=branch, student=s, category=Invoice.Category.TUITION, month=month,
                                  full_amount=D(full), amount=D(amount), paid=D(paid), due_date=month, status=status)


@pytest.fixture
def setup(branch, year, school_class):
    by = make_staff(branch, Role.HEAD_TEACHER, "998900000191")
    math, it = Subject.objects.create(name="Matematika"), Subject.objects.create(name="IT")
    t = make_teacher(branch, "998901110001", "Karimov", category=Teacher.Category.SECOND)
    school_class.homeroom_teacher = t
    school_class.save()
    a, b = student(branch, "Ali", school_class), student(branch, "Bek", school_class)
    invoice(branch, a, "1750000")
    invoice(branch, b, "875000")
    whole = Group.objects.create(branch=branch, academic_year=year, school_class=school_class, code="MAT-4A")
    GroupSubject.objects.create(group=whole, subject=math, teacher=t)
    slot = TimeSlot.objects.create(branch=branch, number=1, start=time(8, 30), end=time(9, 20))
    # Dushanba: 2026-09 da 7, 14, 21, 28 → 4 dars
    Lesson.objects.create(branch=branch, academic_year=year, group=whole, subject=math, teacher=t, weekday=1,
                          slot=slot, valid_from=date(2026, 9, 2), created_by=by)
    aniq = SchoolClass.objects.create(branch=branch, academic_year=year, name="Aniq1", kind="direction")
    sub = Group.objects.create(branch=branch, academic_year=year, school_class=aniq, code="IT-Aniq1-01",
                               kind=Group.Kind.SUBSET, pay_scheme=Group.PayScheme.PER_STUDENT, rate=D("120000"),
                               deduction_percent=D("15"))
    GroupSubject.objects.create(group=sub, subject=it, teacher=t)
    GroupMembership.objects.create(group=sub, student=a, joined_at=date(2026, 9, 2))
    Certificate.objects.create(teacher=t, kind="national", subject=it, issued_on=date(2026, 1, 1),
                               expires_on=date(2028, 1, 1))
    return {"t": t, "by": by, "a": a, "b": b, "math": math, "it": it}


def test_month_payroll_from_db(branch, setup):
    cfg = payroll_settings(branch)
    cfg.homeroom_rate = D("30000")
    cfg.save()
    data = month_payroll(branch, SEP)
    row = next(r for r in data.rows if r.teacher == setup["t"])
    p = row.pay
    assert (p.subjects_count, p.lessons, p.students_count) == (2, 4, 2)
    assert p.base.real == D("14400") + D("120000")                    # 4×2400×1.5 + 120 000
    assert p.category_bonus.real == D("1440")                          # 2-toifa 10% × darsbay
    assert p.certificate_bonus.real == D("36000")                      # 30% × IT
    assert p.deductions.real == D("18000")                             # 15% ushlanma
    assert p.homeroom_bonus == Pair(D("45000"), D("60000"))            # 30 000 × (1 + 0.5) / × 2
    assert p.total.real == D("134400") + D("1440") + D("36000") + D("45000") - D("18000")
    assert data.contracts == 2


def test_lesson_history_teacher_swap(branch, year, setup):
    """O'qituvchi oy o'rtasida almashsa — darslar sanalar bo'yicha bo'linadi."""
    lesson = Lesson.objects.get()
    lesson.valid_to = date(2026, 9, 15)
    lesson.save()
    new = make_teacher(branch, "998901110002", "Yangi")
    Lesson.objects.create(branch=branch, academic_year=year, group=lesson.group, subject=lesson.subject,
                          teacher=new, weekday=1, slot=lesson.slot, valid_from=date(2026, 9, 16),
                          created_by=setup["by"])
    data = month_payroll(branch, SEP)
    pays = {r.teacher.pk: r.pay for r in data.rows}
    assert pays[setup["t"].pk].lessons == 2 and pays[new.pk].lessons == 2
    assert pays[new.pk].base.real == D("7200")


def test_list_only_head_teacher(staff_client):
    assert staff_client.get(reverse("payroll:list")).status_code in (302, 403)


def test_list_page_and_export(head_client, setup):
    resp = head_client.get(reverse("payroll:list"), {"month": "2026-09"})
    html = resp.content.decode()
    assert resp.status_code == 200 and "Sentabr 2026" in html and "Karimov" in html
    assert resp.context["totals"]["lessons"] == 4
    resp = head_client.get(reverse("payroll:export"), {"month": "2026-09"})
    assert resp.status_code == 200 and resp["Content-Disposition"].endswith('oylik-2026-09.xlsx"')
    # noto'g'ri oy — joriy oyga qaytadi
    assert head_client.get(reverse("payroll:list"), {"month": "abc"}).status_code == 200


def test_teacher_page_and_penalties(head_client, branch, setup):
    t = setup["t"]
    url = reverse("payroll:teacher", args=[t.pk]) + "?month=2026-09"
    resp = head_client.get(url)
    assert resp.status_code == 200 and "MAT-4A" in resp.content.decode()
    head_client.post(reverse("payroll:penalty_add", args=[t.pk]), {"month": "2026-09", "amount": "50000",
                                                                   "reason": "Kechikish"})
    p = Penalty.objects.get()
    assert p.month == SEP and p.amount == D("50000")
    assert month_payroll(branch, SEP, teacher=t.pk).rows[0].pay.penalties == D("50000")
    # sababsiz bekor qilinmaydi
    head_client.post(reverse("payroll:penalty_cancel", args=[p.pk]), {"reason": ""})
    p.refresh_from_db()
    assert p.is_active
    head_client.post(reverse("payroll:penalty_cancel", args=[p.pk]), {"reason": "Xato kiritilgan"})
    p.refresh_from_db()
    assert not p.is_active and p.cancel_reason == "Xato kiritilgan"
    assert month_payroll(branch, SEP, teacher=t.pk).rows[0].pay.penalties == 0
    assert Penalty.objects.count() == 1  # o'chirilmaydi


def test_settings_panel(head_client, branch, setup):
    assert head_client.get(reverse("payroll:settings")).status_code == 200
    data = {"first_category_percent": "15", "second_category_percent": "10", "specialist_category_percent": "0",
            "highest_category_percent": "20", "certificate_percent": "30", "language_percent": "15",
            "homeroom_rate": "25000", "next": "/payroll/"}
    head_client.post(reverse("payroll:settings"), data)
    cfg = payroll_settings(branch)
    assert cfg.highest_category_percent == D("20") and cfg.homeroom_rate == D("25000")
    head_client.post(reverse("payroll:settings"), {**data, "certificate_percent": "150"})
    cfg.refresh_from_db()
    assert cfg.certificate_percent == D("30")  # 100% dan oshmaydi


def test_other_branch_teacher_404(head_client, other_branch):
    t = make_teacher(other_branch, "998901110009", "Begona")
    assert head_client.get(reverse("payroll:teacher", args=[t.pk])).status_code == 404


def test_salary_payment_status_and_expense(head_client, branch, setup):
    from apps.finance.models import Expense, Transaction
    from apps.payroll.models import SalaryPayment
    t = setup["t"]
    url = reverse("payroll:salary_pay", args=[t.pk])
    head_client.post(url, {"month": "2026-09", "kind": "advance", "amount": "40000", "account_kind": "bank",
                           "paid_on": "2026-09-26"})
    pay = SalaryPayment.objects.get()
    assert pay.month == SEP and pay.expense.category.name == "Ish haqi"
    assert Transaction.objects.get(expense=pay.expense).direction == Transaction.Direction.OUT
    resp = head_client.get(reverse("payroll:teacher", args=[t.pk]), {"month": "2026-09"})
    st = resp.context["status"]
    assert st["paid"] == D("40000") and st["key"] == "partial" and st["left"] == st["accrued"] - D("40000")
    # naqd — kassa yopiq bo'lsa berilmaydi
    head_client.post(url, {"month": "2026-09", "kind": "salary", "amount": "1000", "account_kind": "cash",
                           "paid_on": "2026-09-29"})
    assert SalaryPayment.objects.count() == 1 and Expense.objects.count() == 1
    # kelgusi oy uchun berilmaydi
    head_client.post(url, {"month": "2099-01", "kind": "salary", "amount": "1000", "account_kind": "bank",
                           "paid_on": "2026-09-29"})
    assert SalaryPayment.objects.count() == 1


def test_teacher_export(head_client, setup):
    resp = head_client.get(reverse("payroll:teacher_export", args=[setup["t"].pk]), {"month": "2026-09"})
    assert resp.status_code == 200 and "oylik-" in resp["Content-Disposition"]


def test_my_salary_page(client, branch, setup):
    from apps.accounts.models import UserRole
    from apps.payroll.services.payments import pay_salary
    t = setup["t"]
    UserRole.objects.create(user=t.user, role=Role.TEACHER, branch=branch)
    pay_salary(branch=branch, teacher=t, month=SEP, kind="advance", amount=D("40000"), account_kind="bank",
               paid_on=date(2026, 9, 15), by=setup["by"])
    pay_salary(branch=branch, teacher=t, month=SEP, kind="salary", amount=D("60000"), account_kind="bank",
               paid_on=date(2026, 9, 29), by=setup["by"])
    client.force_login(t.user)
    resp = client.get(reverse("payroll:my_salary"))
    h = resp.context["history"]
    assert resp.status_code == 200 and h["total"] == D("100000") and h["count"] == 2
    assert [m["month"] for m in h["months"]] == [SEP] and h["months"][0]["items"][0].kind == "salary"
    assert "Avans" in resp.content.decode()
