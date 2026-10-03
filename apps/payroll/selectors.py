"""Oylik hisob-kitobi uchun ma'lumot yig'ish: bazadan o'qiydi, hisobni `domain.calc` qiladi.

Bitta oy uchun butun filial bir necha so'rovda yuklanadi (o'qituvchilar soni oshsa ham so'rovlar ko'paymaydi).
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Q

from apps.academics.models import Group, GroupMembership, GroupSubject, Language, Lesson, SchoolClass
from apps.academics.selectors import lesson_occurrences
from apps.finance.models import Invoice
from apps.people.models import Certificate, Student, Teacher

from .domain.calc import Homeroom, Line, Pair, Rates, StudentShare, TeacherPay
from .models import PayrollSettings, Penalty, SalaryPayment


def month_bounds(month: date) -> tuple[date, date]:
    first = month.replace(day=1)
    return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])


def payroll_settings(branch) -> PayrollSettings:
    obj, _ = PayrollSettings.objects.get_or_create(branch=branch)
    return obj


@dataclass
class TeacherRow:
    teacher: Teacher
    pay: TeacherPay


@dataclass
class MonthPayroll:
    month: date
    rows: list[TeacherRow]
    contracts: int

    def column(self, name: str) -> Pair:
        total = Pair()
        for r in self.rows:
            total += getattr(r.pay, name)
        return total

    @property
    def totals(self) -> dict:
        names = ("base", "category_bonus", "certificate_bonus", "language_bonus", "bonuses", "deductions",
                 "homeroom_bonus", "total")
        return {
            **{n: self.column(n) for n in names},
            "subjects": sum(r.pay.subjects_count for r in self.rows),
            "lessons": sum(r.pay.lessons for r in self.rows),
            "students": sum(r.pay.students_count for r in self.rows),
        }


def month_payroll(branch, month: date, *, teacher: int | None = None) -> MonthPayroll:
    start, end = month_bounds(month)
    cfg = payroll_settings(branch)

    # --- To'lov grafigi: o'quvchi → shu oy ulushi ---
    invoices = (Invoice.objects.filter(branch=branch, category=Invoice.Category.TUITION, month=start)
                .exclude(status=Invoice.Status.CANCELLED).select_related("student"))
    shares = {i.student_id: StudentShare(i.student_id, i.student.full_name, i.paid, i.amount, i.full_amount)
              for i in invoices}

    groups = Group.objects.filter(branch=branch, academic_year__start_date__lte=end,
                                  academic_year__end_date__gte=start)

    # --- Guruh o'quvchilari: butun sinf — sinfdan, tanlov — oy bilan kesishgan a'zoliklardan ---
    class_students: dict[int, list[int]] = defaultdict(list)
    for sid, cid in Student.objects.filter(pk__in=shares.keys(), school_class__isnull=False).values_list(
            "pk", "school_class_id"):
        class_students[cid].append(sid)
    members: dict[int, list[int]] = defaultdict(list)
    for gid, sid in (GroupMembership.objects.filter(group__in=groups, student_id__in=shares.keys(),
                                                    joined_at__lte=end)
                     .filter(Q(left_at__isnull=True) | Q(left_at__gte=start)).values_list("group_id", "student_id")):
        members[gid].append(sid)

    # --- Darslar: (o'qituvchi, guruh, fan) → shu oyda o'tiladigan darslar (jadval tarixi bilan) ---
    lessons: dict[tuple[int, int, int], int] = defaultdict(int)
    lesson_qs = (Lesson.objects.filter(branch=branch, valid_from__lte=end)
                 .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=start)))
    if teacher:
        lesson_qs = lesson_qs.filter(teacher_id=teacher)
    for lesson in lesson_qs.only("teacher_id", "group_id", "subject_id", "weekday", "valid_from", "valid_to"):
        lessons[(lesson.teacher_id, lesson.group_id, lesson.subject_id)] += lesson_occurrences(lesson, start, end)

    # Qatorlar: hozirgi guruh fanlari + oy ichida dars o'tgan (o'qituvchi almashgan bo'lsa ham) juftliklar
    gs_qs = GroupSubject.objects.filter(group__in=groups).select_related("group__school_class", "subject")
    if teacher:
        gs_qs = gs_qs.filter(teacher_id=teacher)
    pairs: dict[tuple[int, int, int], GroupSubject | None] = {}
    for gs in gs_qs:
        if gs.group.is_active or lessons.get((gs.teacher_id, gs.group_id, gs.subject_id)):
            pairs[(gs.teacher_id, gs.group_id, gs.subject_id)] = gs
    extra = [k for k in lessons if k not in pairs and lessons[k]]
    if extra:
        by_gs = {(gs.group_id, gs.subject_id): gs for gs in GroupSubject.objects.filter(
            group_id__in={k[1] for k in extra}).select_related("group__school_class", "subject")}
        for k in extra:
            pairs[k] = by_gs.get((k[1], k[2]))

    lines: dict[int, list[Line]] = defaultdict(list)
    for (tid, gid, subid), gs in pairs.items():
        if gs is None:  # fan guruhdan olib tashlangan — darsbay hisobga guruh ma'lumoti kerak
            continue
        g = gs.group
        per_lesson = g.pay_scheme == Group.PayScheme.PER_LESSON
        sids = class_students.get(g.school_class_id, []) if g.kind == Group.Kind.WHOLE_CLASS else members.get(gid, [])
        lines[tid].append(Line(
            group_id=gid, group_code=g.code, class_name=g.school_class.name, subject_id=subid,
            subject_name=gs.subject.name, per_lesson=per_lesson, rate=g.rate, deduction_percent=g.deduction_percent,
            lessons=lessons.get((tid, gid, subid), 0), foreign=g.school_class.language != Language.UZ,
            students=sorted((shares[s] for s in sids), key=lambda s: s.name)))

    # --- Sertifikatlar (oy ichida amal qilgan), sinf rahbarligi, jarimalar ---
    certs: dict[int, set] = defaultdict(set)
    for tid, subid in Certificate.objects.filter(teacher__branch=branch, issued_on__lte=end,
                                                 expires_on__gte=start).values_list("teacher_id", "subject_id"):
        certs[tid].add(subid)
    homerooms: dict[int, list[Homeroom]] = defaultdict(list)
    for c in SchoolClass.objects.filter(branch=branch, homeroom_teacher__isnull=False, is_active=True,
                                        academic_year__start_date__lte=end, academic_year__end_date__gte=start):
        students = sorted((shares[s] for s in class_students.get(c.pk, [])), key=lambda x: x.name)
        homerooms[c.homeroom_teacher_id].append(Homeroom(c.name, students))
    penalties: dict[int, Decimal] = defaultdict(Decimal)
    for p in Penalty.objects.filter(branch=branch, month=start, cancelled_at__isnull=True):
        penalties[p.teacher_id] += p.amount

    # --- O'qituvchilar: ishlayotganlar + shu oyda summasi borlar ---
    ids = set(lines) | set(homerooms) | set(penalties)
    tq = Teacher.objects.filter(branch=branch).filter(
        Q(pk__in=ids) | Q(status__in=[Teacher.Status.ACTIVE, Teacher.Status.VACATION])).select_related("user")
    if teacher:
        tq = tq.filter(pk=teacher)
    rows = []
    for t in tq:
        subjects = certs.get(t.pk, set())
        pay = TeacherPay(
            teacher_id=t.pk,
            rates=Rates(cfg.category_percent(t.category), cfg.certificate_percent, cfg.language_percent,
                        cfg.homeroom_rate),
            lines=sorted(lines.get(t.pk, []), key=lambda x: (x.class_name, x.group_code, x.subject_name)),
            fixed_salary=t.fixed_salary or Decimal("0"),
            cert_subjects=frozenset(s for s in subjects if s), cert_all_subjects=None in subjects,
            homerooms=homerooms.get(t.pk, []), penalties=penalties.get(t.pk, Decimal("0")))
        if not pay.is_empty or t.status == Teacher.Status.ACTIVE:
            rows.append(TeacherRow(t, pay))
    rows.sort(key=lambda r: (-r.pay.total.real, r.teacher.user.last_name))
    return MonthPayroll(month=start, rows=rows, contracts=len(shares))


def teacher_penalties(branch, teacher, month: date):
    return (Penalty.objects.filter(branch=branch, teacher=teacher, month=month_bounds(month)[0])
            .select_related("created_by", "cancelled_by"))


def teacher_payments(branch, teacher, month: date):
    return (SalaryPayment.objects.filter(branch=branch, teacher=teacher, month=month_bounds(month)[0])
            .select_related("expense__account", "created_by"))


def payment_status(accrued: Decimal, paid: Decimal) -> dict:
    """To'lov holati: hisoblangan (real oylik) va berilgan pul bo'yicha."""
    accrued = accrued.quantize(Decimal("1"))
    left = accrued - paid
    if paid <= 0:
        key, label = "pending", "Kutilmoqda"
    elif left > 0:
        key, label = "partial", "Qisman berilgan"
    elif left == 0:
        key, label = "paid", "To'liq berilgan"
    else:
        key, label = "over", "Ortiqcha berilgan"
    return {"accrued": accrued, "paid": paid, "left": left, "key": key, "label": label}


def teacher_payment_history(branch, teacher) -> dict:
    """O'qituvchiga berilgan barcha pullar: jami, soni va oylar bo'yicha guruhlar (yangisi tepada)."""
    payments = list(SalaryPayment.objects.filter(branch=branch, teacher=teacher)
                    .select_related("expense__account", "branch").order_by("-month", "-paid_on", "-created_at"))
    months: dict[date, dict] = {}
    for p in payments:
        m = months.setdefault(p.month, {"month": p.month, "total": Decimal("0"), "items": []})
        m["total"] += p.amount
        m["items"].append(p)
    return {"total": sum((p.amount for p in payments), Decimal("0")), "count": len(payments),
            "months": list(months.values())}
