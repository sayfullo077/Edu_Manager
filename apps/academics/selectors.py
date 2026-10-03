"""Sinflar va guruhlar: o'qish so'rovlari. Har doim filial bilan cheklangan.

Guruh a'zolari:
- butun sinf guruhi (`whole_class`) — sinfning faol o'quvchilari (alohida yozilmaydi, sinfdan olinadi);
- tanlov guruhi (`subset`) — `GroupMembership` (chiqqanlar `left_at` bilan tarixda qoladi — oylik uchun kerak).
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Count, IntegerField, OuterRef, Prefetch, Q, QuerySet, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.core.models import AcademicYear
from apps.people.models import Student, StudentGuardian, Teacher

from .models import (
    ClassAttendance,
    Group,
    GroupMembership,
    GroupSubject,
    Lesson,
    Room,
    SchoolClass,
    Subject,
    TimeSlot,
    Weekday,
)

ACTIVE = Student.Status.ACTIVE


@dataclass(frozen=True)
class ClassFilters:
    year: int | None = None
    kind: str = ""
    language: str = ""
    q: str = ""


def _active_students_in_class(outer: str) -> Subquery:
    sub = (Student.objects.filter(school_class=OuterRef(outer), status=ACTIVE).order_by()
           .values("school_class").annotate(c=Count("pk")).values("c")[:1])
    return Coalesce(Subquery(sub, output_field=IntegerField()), 0)


def _active_members(outer: str = "pk") -> Subquery:
    sub = (GroupMembership.objects.filter(group=OuterRef(outer), left_at__isnull=True,
                                          student__status=ACTIVE).order_by()
           .values("group").annotate(c=Count("pk")).values("c")[:1])
    return Coalesce(Subquery(sub, output_field=IntegerField()), 0)


def classes_list(branch, f: ClassFilters) -> QuerySet[SchoolClass]:
    qs = (SchoolClass.objects.filter(branch=branch)
          .select_related("homeroom_teacher__user", "room", "academic_year")
          .annotate(n_students=_active_students_in_class("pk"),
                    n_groups=Count("groups", filter=Q(groups__is_active=True), distinct=True)))
    if f.year:
        qs = qs.filter(academic_year_id=f.year)
    if f.kind:
        qs = qs.filter(kind=f.kind)
    if f.language:
        qs = qs.filter(language=f.language)
    for term in f.q.split()[:3]:
        qs = qs.filter(Q(name__icontains=term) | Q(homeroom_teacher__user__last_name__icontains=term))
    return qs.order_by("-is_active", "kind", "grade", "name")


def groups_list(branch, f: ClassFilters, *, school_class: int | None = None) -> QuerySet[Group]:
    qs = (Group.objects.filter(branch=branch)
          .select_related("school_class", "room")
          .prefetch_related(Prefetch("subjects", queryset=GroupSubject.objects
                                     .select_related("subject", "teacher__user").order_by("pk")))
          .annotate(n_members=_active_members(), n_class=_active_students_in_class("school_class")))
    if f.year:
        qs = qs.filter(academic_year_id=f.year)
    if school_class:
        qs = qs.filter(school_class_id=school_class)
    if f.kind:
        qs = qs.filter(school_class__kind=f.kind)
    if f.language:
        qs = qs.filter(school_class__language=f.language)
    for term in f.q.split()[:3]:
        qs = qs.filter(Q(code__icontains=term) | Q(school_class__name__icontains=term)
                       | Q(subjects__subject__name__icontains=term)
                       | Q(subjects__teacher__user__last_name__icontains=term))
    return qs.distinct().order_by("-is_active", "school_class__grade", "school_class__name", "code")


def member_count(group: Group) -> int:
    """Guruhdagi faol o'quvchilar soni (butun sinf — sinfdan, tanlov guruhi — a'zolikdan)."""
    if hasattr(group, "n_members"):
        return group.n_class if group.kind == Group.Kind.WHOLE_CLASS else group.n_members
    return group_members(group).count() if group.kind == Group.Kind.WHOLE_CLASS else (
        group.memberships.filter(left_at__isnull=True, student__status=ACTIVE).count())


def stats(branch, year_id: int | None) -> dict:
    classes = SchoolClass.objects.filter(branch=branch, is_active=True)
    groups = Group.objects.filter(branch=branch, is_active=True)
    if year_id:
        classes, groups = classes.filter(academic_year_id=year_id), groups.filter(academic_year_id=year_id)
    return {
        "classes": classes.count(),
        "no_homeroom": classes.filter(homeroom_teacher__isnull=True).count(),
        "groups": groups.count(),
        "subset_groups": groups.filter(kind=Group.Kind.SUBSET).count(),
        "students": Student.objects.filter(school_class__in=classes, status=ACTIVE).count(),
        "without_class": Student.objects.filter(branch=branch, status=ACTIVE, school_class__isnull=True).count(),
    }


def class_detail(branch, pk: int) -> SchoolClass:
    return (SchoolClass.objects.select_related("homeroom_teacher__user", "room", "academic_year")
            .annotate(n_students=_active_students_in_class("pk")).get(branch=branch, pk=pk))


def class_students(school_class: SchoolClass) -> QuerySet[Student]:
    return school_class.students.filter(status=ACTIVE).order_by("last_name", "first_name")


def group_detail(branch, pk: int) -> Group:
    return (Group.objects.select_related("school_class__academic_year", "room", "academic_year")
            .prefetch_related(Prefetch("subjects", queryset=GroupSubject.objects
                                       .select_related("subject", "teacher__user").order_by("pk")))
            .annotate(n_members=_active_members(), n_class=_active_students_in_class("school_class"))
            .get(branch=branch, pk=pk))


def group_members(group: Group):
    """Butun sinf — sinf o'quvchilari (Student); tanlov guruhi — faol a'zoliklar (GroupMembership)."""
    if group.kind == Group.Kind.WHOLE_CLASS:
        return class_students(group.school_class).select_related("school_class")
    return (group.memberships.filter(left_at__isnull=True, student__status=ACTIVE)
            .select_related("student__school_class").order_by("student__last_name", "student__first_name"))


def group_history(group: Group) -> QuerySet[GroupMembership]:
    return group.memberships.filter(left_at__isnull=False).select_related("student").order_by("-left_at")


def subject_busy_students(group: Group) -> QuerySet:
    """Shu guruh fanlaridan biri bo'yicha BOSHQA faol tanlov guruhida o'qiyotgan o'quvchilar (id).

    Qoida (asl tizim): har bir o'quvchi bir fan bo'yicha faqat bitta guruhga biriktiriladi.
    """
    subject_ids = group.subjects.values("subject_id")
    return (GroupMembership.objects.filter(left_at__isnull=True, group__is_active=True, group__kind=Group.Kind.SUBSET,
                                           group__academic_year_id=group.academic_year_id,
                                           group__subjects__subject_id__in=subject_ids)
            .exclude(group=group).values("student_id"))


def member_candidates(group: Group, *, all_classes: bool = False) -> QuerySet[Student]:
    """Tanlov guruhiga qo'shish mumkin bo'lganlar: faol, shu filial, hozir a'zo emas, shu fan bo'yicha boshqa
    guruhda ham emas. Sukut — guruh sinfidan."""
    current = group.memberships.filter(left_at__isnull=True).values("student")
    qs = (Student.objects.filter(branch=group.branch, status=ACTIVE).exclude(pk__in=current)
          .exclude(pk__in=subject_busy_students(group)).select_related("school_class"))
    if not all_classes:
        qs = qs.filter(school_class=group.school_class)
    return qs.order_by("school_class__name", "last_name", "first_name")


def student_groups(student: Student) -> list[Group]:
    """O'quvchi kartasi uchun: faol tanlov guruhlari + o'z sinfining butun sinf guruhlari."""
    prefetch = Prefetch("subjects", queryset=GroupSubject.objects.select_related("subject", "teacher__user"))
    cond = Q(memberships__student=student, memberships__left_at__isnull=True)
    if student.school_class_id:
        cond |= Q(kind=Group.Kind.WHOLE_CLASS, school_class_id=student.school_class_id)
    return list(Group.objects.filter(cond, is_active=True).distinct().select_related("school_class")
                .prefetch_related(prefetch).order_by("code"))


# ---------- Forma tanlovlari ----------

def teacher_choices(branch) -> QuerySet[Teacher]:
    return (Teacher.objects.filter(branch=branch).exclude(status__in=Teacher.NOT_WORKING)
            .select_related("user").order_by("user__last_name", "user__first_name"))


def room_choices(branch) -> QuerySet[Room]:
    return Room.objects.filter(branch=branch, is_active=True).order_by("name")


def subject_choices() -> QuerySet[Subject]:
    return Subject.objects.filter(is_active=True).order_by("name", "language")


def class_choices(branch) -> QuerySet[SchoolClass]:
    return (SchoolClass.objects.filter(branch=branch, is_active=True).select_related("academic_year")
            .order_by("-academic_year__start_date", "kind", "grade", "name"))


def year_choices() -> QuerySet[AcademicYear]:
    return AcademicYear.objects.order_by("-start_date")


# ---------- Dars jadvali ----------

def week_start(day: date) -> date:
    """Dushanba. Yakshanba — keyingi haftaning boshiga emas, o'tgan hafta (Dush–Shan) ga tegishli."""
    return day - timedelta(days=day.weekday())


def timetable_grid(branch, *, week: date, school_class: int | None = None, teacher: int | None = None,
                   room: int | None = None) -> dict:
    """Haftalik to'r: qatorlar — dars vaqtlari, ustunlar — Dushanba–Shanba (aniq sanalar bilan).

    Har bir katakda o'sha kuni amal qiladigan darslar (tarix: valid_from/valid_to).
    """
    monday = week_start(week)
    days = [(wd, monday + timedelta(days=wd - 1)) for wd, _ in Weekday.choices]
    saturday = days[-1][1]
    qs = (Lesson.objects.filter(branch=branch, valid_from__lte=saturday)
          .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=monday))
          .select_related("group__school_class", "subject", "teacher__user", "room", "slot"))
    if school_class:
        qs = qs.filter(group__school_class_id=school_class)
    if teacher:
        qs = qs.filter(teacher_id=teacher)
    if room:
        qs = qs.filter(room_id=room)
    slots = list(TimeSlot.objects.filter(branch=branch).order_by("number"))
    cells = {(s.pk, wd): [] for s in slots for wd, _ in days}
    day_of = dict(days)
    total = 0
    for lesson in qs:
        if lesson.active_on(day_of[lesson.weekday]) and (lesson.slot_id, lesson.weekday) in cells:
            cells[(lesson.slot_id, lesson.weekday)].append(lesson)
            total += 1
    rows = [{"slot": s, "cells": [{"weekday": wd, "date": d, "lessons": cells[(s.pk, wd)]} for wd, d in days]}
            for s in slots]
    return {"days": [{"weekday": wd, "label": Weekday(wd).label, "date": d} for wd, d in days], "rows": rows,
            "total": total, "monday": monday, "saturday": saturday}


def lesson_count(qs, date_from: date, date_to: date) -> int:
    """Davrda o'tiladigan darslar soni (jadval bo'yicha, tarix hisobga olinadi). Darsbay oylik uchun.

    Bayram/dars qoldirilishi hali hisobga olinmaydi.
    """
    qs = qs.filter(valid_from__lte=date_to).filter(Q(valid_to__isnull=True) | Q(valid_to__gte=date_from))
    return sum(lesson_occurrences(lesson, date_from, date_to) for lesson in qs)


def lesson_occurrences(lesson, date_from: date, date_to: date) -> int:
    """Bitta jadval yozuvi davr ichida necha marta o'tiladi (valid_from/valid_to hisobga olinadi)."""
    start = max(date_from, lesson.valid_from)
    end = min(date_to, lesson.valid_to) if lesson.valid_to else date_to
    first = start + timedelta(days=(lesson.weekday - 1 - start.weekday()) % 7)  # birinchi mos hafta kuni
    return (end - first).days // 7 + 1 if first <= end else 0


def timetable_targets(branch, year) -> dict:
    """Filtrlar uchun: sinflar (shu yil), o'qituvchilar, xonalar."""
    return {
        "classes": SchoolClass.objects.filter(branch=branch, is_active=True, academic_year=year)
        .order_by("kind", "grade", "name"),
        "teachers": teacher_choices(branch),
        "rooms": room_choices(branch),
    }


def lesson_detail(branch, pk: int) -> Lesson:
    return (Lesson.objects.select_related("group__school_class", "subject", "teacher__user", "room", "slot",
                                          "academic_year", "created_by").get(branch=branch, pk=pk))


def groups_for_cell(branch, year, *, school_class: int | None = None):
    qs = (Group.objects.filter(branch=branch, academic_year=year, is_active=True).select_related("school_class")
          .prefetch_related(Prefetch("subjects", queryset=GroupSubject.objects
                                     .select_related("subject", "teacher__user"))))
    if school_class:
        qs = qs.filter(school_class_id=school_class)
    return qs.order_by("school_class__grade", "school_class__name", "code")


def subject_cards(branch, school_class: SchoolClass, *, week: date) -> dict:
    """Jadval uchun fan kartalari: sinf guruhlarining fanlari. Bir fan bir nechta tanlov guruhida bo'lsa —
    bitta "hovuz" karta (sinf bo'lingan, darslar bir vaqtda). `placed` — ko'rsatilgan haftada qo'yilganlar.
    """
    monday = week_start(week)
    saturday = monday + timedelta(days=5)
    groups = list(groups_for_cell(branch, school_class.academic_year, school_class=school_class.pk)
                  .select_related("room", "school_class__room"))
    week_lessons = (Lesson.objects.filter(group__in=groups, valid_from__lte=saturday)
                    .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=monday)))
    placed: dict[tuple[int, int], set] = {}
    for lesson in week_lessons:
        day = monday + timedelta(days=lesson.weekday - 1)
        if lesson.active_on(day):
            placed.setdefault((lesson.group_id, lesson.subject_id), set()).add((lesson.weekday, lesson.slot_id))
    cards: dict[tuple, dict] = {}
    for g in groups:
        for gs in g.subjects.all():
            # Butun sinf guruhi — alohida karta; tanlov guruhlari bir fan bo'yicha — hovuz
            key = (gs.subject_id, "pool") if g.kind == Group.Kind.SUBSET else (gs.subject_id, g.pk)
            card = cards.setdefault(key, {"subject": gs.subject, "parts": [], "hours": 0, "slots": set()})
            room = g.room or g.school_class.room
            card["parts"].append({"group": g, "teacher": gs.teacher, "room": room,
                                  "room_label": "guruh xonasi" if g.room else "sinf xonasi"})
            card["hours"] = max(card["hours"], gs.hours_per_week)
            card["slots"] |= placed.get((g.pk, gs.subject_id), set())
    result = []
    for card in cards.values():
        card["placed"] = len(card["slots"])
        card["pool"] = len(card["parts"]) > 1
        card["full"] = bool(card["hours"]) and card["placed"] >= card["hours"]
        card["group_ids"] = ",".join(str(p["group"].pk) for p in card["parts"])
        result.append(card)
    result.sort(key=lambda c: (c["full"], c["subject"].name))
    return {"cards": result, "hours": sum(c["hours"] for c in result),
            "placed": sum(min(c["placed"], c["hours"]) if c["hours"] else c["placed"] for c in result)}


# ---------- O'qituvchi paneli ----------

def teacher_profile(user, branch) -> Teacher | None:
    return Teacher.objects.filter(user=user, branch=branch).select_related("user").first()


def lessons_on(branch, teacher: Teacher, day: date) -> list[dict]:
    """O'qituvchining shu kungi darslari (jadval tarixi bilan), vaqt bo'yicha. Holat: o'tdi / hozir / kutilmoqda."""
    if day.isoweekday() not in Weekday.values:
        return []
    qs = (Lesson.objects.filter(branch=branch, teacher=teacher, weekday=day.isoweekday(), valid_from__lte=day)
          .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=day))
          .select_related("group__school_class", "subject", "room", "slot").order_by("slot__start"))
    now = timezone.localtime()
    is_today = day == now.date()
    result = []
    for lesson in qs:
        if not is_today:
            state = "done" if day < now.date() else "waiting"
        elif now.time() >= lesson.slot.end:
            state = "done"
        elif now.time() >= lesson.slot.start:
            state = "now"
        else:
            state = "waiting"
        result.append({"lesson": lesson, "state": state})
    return result


def teacher_groups(branch, teacher: Teacher) -> list[Group]:
    """O'qituvchining faol tanlov guruhlari: hamma fanlar (Birlashma), o'zi o'qitadiganlari (`my_subjects`),
    faol a'zolar soni va to'lish foizi."""
    groups = list(
        Group.objects.filter(branch=branch, is_active=True, kind=Group.Kind.SUBSET, subjects__teacher=teacher)
        .distinct().select_related("school_class", "room", "school_class__room")
        .prefetch_related(Prefetch("subjects", queryset=GroupSubject.objects.select_related("subject")
                                   .order_by("subject__name")))
        .annotate(n_members=Count("memberships", filter=Q(memberships__left_at__isnull=True), distinct=True))
        .order_by("code"))
    for g in groups:
        subjects = list(g.subjects.all())
        g.all_subjects = [gs.subject for gs in subjects]
        g.my_subjects = [gs.subject for gs in subjects if gs.teacher_id == teacher.pk]
        g.percent = min(100, round(g.n_members * 100 / g.capacity)) if g.capacity else 0
    return groups


def teacher_group(branch, teacher: Teacher, pk: int) -> Group | None:
    return next((g for g in teacher_groups(branch, teacher) if g.pk == pk), None)


def group_assign_stats(group: Group, candidates) -> dict:
    """«Statistika: Jami N o'quvchi · Biriktirilgan · Bo'sh» (asl tizimdagidek, guruh sinfi bo'yicha)."""
    total = Student.objects.filter(school_class=group.school_class, status=ACTIVE).count()
    return {"total": total, "assigned": group.n_members, "free": candidates.count(),
            "seats": max(group.capacity - group.n_members, 0)}


def teacher_dashboard(branch, teacher: Teacher, today: date) -> dict:
    """O'qituvchi bosh sahifasi: bugungi darslar, o'quvchilar, haftalik darslar, guruhlar (tanlov guruhlari)."""
    today_lessons = lessons_on(branch, teacher, today)
    upcoming = [x for x in today_lessons if x["state"] == "waiting"]
    monday = week_start(today)
    week_qs = Lesson.objects.filter(branch=branch, teacher=teacher)
    groups = teacher_groups(branch, teacher)
    students = (GroupMembership.objects.filter(group__in=groups, left_at__isnull=True)
                .values("student").distinct().count())
    return {
        "today_lessons": today_lessons,
        "next_lesson": upcoming[0]["lesson"] if upcoming else None,
        "week_lessons": lesson_count(week_qs, monday, monday + timedelta(days=5)),
        "groups": groups, "students": students,
    }


def week_day_lessons(grid: dict) -> list[dict]:
    """timetable_grid → kunlar bo'yicha ro'yxat (telefon ko'rinishi): [{label, date, lessons: [(slot, lesson)]}]."""
    days = [{"label": d["label"], "date": d["date"], "lessons": []} for d in grid["days"]]
    for row in grid["rows"]:
        if row["slot"].is_break:
            continue
        for i, cell in enumerate(row["cells"]):
            days[i]["lessons"].extend((row["slot"], lesson) for lesson in cell["lessons"])
    return days


# ---------- Sinf rahbarlik ----------

WEEKDAY_SHORT = ["Du", "Se", "Cho", "Pa", "Ju", "Sha", "Ya"]


def homeroom_classes(branch, teacher: Teacher, today: date) -> list[SchoolClass]:
    """O'qituvchi rahbar bo'lgan faol sinflar: o'quvchilar soni va bugungi davomat holati."""
    classes = list(SchoolClass.objects.filter(branch=branch, homeroom_teacher=teacher, is_active=True)
                   .order_by("grade", "name"))
    for c in classes:
        c.n_students = class_students(c).count()
        c.n_marked = ClassAttendance.objects.filter(school_class=c, date=today,
                                                    student__in=class_students(c)).count()
        c.att_state = ("none" if not c.n_marked else "full" if c.n_marked >= c.n_students else "partial")
    return classes


def homeroom_class(branch, teacher: Teacher, pk: int) -> SchoolClass | None:
    return SchoolClass.objects.filter(branch=branch, homeroom_teacher=teacher, is_active=True, pk=pk).first()


def class_day_sheet(school_class: SchoolClass, day: date) -> list[dict]:
    """Kunlik davomat: o'quvchi, asosiy vasiysi (ism · telefon), belgi va izoh."""
    students = list(class_students(school_class).order_by("last_name", "first_name"))
    marks = {a.student_id: a for a in ClassAttendance.objects.filter(student__in=students, date=day)}
    guardians: dict[int, object] = {}
    for link in (StudentGuardian.objects.filter(student__in=students).select_related("guardian")
                 .order_by("-is_primary", "pk")):
        guardians.setdefault(link.student_id, link.guardian)
    return [{"student": s, "guardian": guardians.get(s.pk), "mark": marks.get(s.pk)} for s in students]


def class_month_stats(school_class: SchoolClass, month: date, today: date) -> dict:
    """Oylik statistika: o'quvchi × kun (bugungacha), har belgi jami va kelish foizi."""
    first = month.replace(day=1)
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    end = min(last, today)
    days = []
    d = first
    while d <= end:
        days.append({"date": d, "label": WEEKDAY_SHORT[d.weekday()], "weekend": d.weekday() == 6,
                     "today": d == today})
        d += timedelta(days=1)
    students = list(class_students(school_class).order_by("last_name", "first_name"))
    marks = {(a.student_id, a.date): a.status for a in ClassAttendance.objects.filter(
        student__in=students, date__range=(first, last))}
    rows, totals_all = [], dict.fromkeys(ClassAttendance.Status.values, 0)
    for s in students:
        cells = [marks.get((s.pk, x["date"]), "") for x in days]
        totals = {k: cells.count(k) for k in ClassAttendance.Status.values}
        marked = sum(totals.values())
        came = totals["B"] + totals["K"]
        rows.append({"student": s, "cells": cells, "totals": totals,
                     "percent": round(came * 100 / marked) if marked else None})
        for k, v in totals.items():
            totals_all[k] += v
    marked_all = sum(totals_all.values())
    return {"days": days, "rows": rows, "totals": totals_all, "month": first,
            "percent": round((totals_all["B"] + totals_all["K"]) * 100 / marked_all) if marked_all else None}
