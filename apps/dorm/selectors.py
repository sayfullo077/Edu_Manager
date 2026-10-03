"""Yotoqxona o'qish so'rovlari."""

from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Count, Exists, OuterRef, Q, QuerySet, Sum

from apps.people.models import Student

from .models import DormAttendance, DormRoom, DormStay

ACTIVE = Q(stays__checked_out__isnull=True)


def occupancy(branch) -> dict:
    """Boshqaruv paneli: xonalar, o'rinlar, band, bo'sh, bandlik % va jins bo'yicha xonalar."""
    rooms = DormRoom.objects.filter(branch=branch, status=DormRoom.Status.ACTIVE)
    s = rooms.aggregate(
        rooms=Count("id"), capacity=Sum("capacity"),
        male=Count("id", filter=Q(gender=DormRoom.Gender.MALE)),
        female=Count("id", filter=Q(gender=DormRoom.Gender.FEMALE)),
        mixed=Count("id", filter=Q(gender=DormRoom.Gender.MIXED)))
    s["capacity"] = s["capacity"] or 0
    s["occupied"] = DormStay.objects.filter(room__in=rooms, checked_out__isnull=True).count()
    s["free"] = max(s["capacity"] - s["occupied"], 0)
    s["percent"] = round(s["occupied"] * 100 / s["capacity"]) if s["capacity"] else 0
    return s


@dataclass(frozen=True)
class ResidentFilters:
    q: str = ""
    room: int | None = None
    gender: str = ""
    date_from: date | None = None
    date_to: date | None = None


def residents(branch, f: ResidentFilters) -> QuerySet[DormStay]:
    """Hozir yashayotganlar (chiqmagan qaydlar)."""
    qs = (DormStay.objects.filter(room__branch=branch, checked_out__isnull=True)
          .select_related("student__branch", "student__school_class", "room__branch"))
    if f.room:
        qs = qs.filter(room_id=f.room)
    if f.gender:
        qs = qs.filter(student__gender=f.gender)
    if f.date_from:
        qs = qs.filter(checked_in__gte=f.date_from)
    if f.date_to:
        qs = qs.filter(checked_in__lte=f.date_to)
    for term in f.q.split()[:5]:
        qs = qs.filter(Q(student__last_name__icontains=term) | Q(student__first_name__icontains=term)
                       | Q(student__middle_name__icontains=term) | Q(student__code__icontains=term))
    return qs.order_by("room__name", "student__last_name", "student__first_name")


def room_choices(branch) -> QuerySet[DormRoom]:
    return DormRoom.objects.filter(branch=branch).order_by("name")


# ---------- Xonalar ro'yxati ----------

@dataclass(frozen=True)
class RoomFilters:
    q: str = ""
    status: str = ""
    gender: str = ""
    room_type: int | None = None


def rooms_list(branch, f: RoomFilters) -> QuerySet[DormRoom]:
    qs = DormRoom.objects.filter(branch=branch).annotate(occupied=Count("stays", filter=ACTIVE))
    if f.status:
        qs = qs.filter(status=f.status)
    if f.gender:
        qs = qs.filter(gender=f.gender)
    if f.room_type:
        qs = qs.filter(room_type=f.room_type)
    if f.q:
        qs = qs.filter(Q(name__icontains=f.q) | Q(floor__icontains=f.q))
    return qs.order_by("name")


def rooms_stats(branch) -> dict:
    return DormRoom.objects.filter(branch=branch).aggregate(
        total=Count("id"), active=Count("id", filter=Q(status=DormRoom.Status.ACTIVE)),
        inactive=Count("id", filter=Q(status=DormRoom.Status.INACTIVE)),
        repair=Count("id", filter=Q(status=DormRoom.Status.REPAIR)))


def room_detail(branch, pk: int) -> DormRoom:
    return DormRoom.objects.annotate(occupied=Count("stays", filter=ACTIVE)).get(branch=branch, pk=pk)


def room_residents(room) -> QuerySet[DormStay]:
    return (room.stays.filter(checked_out__isnull=True).select_related("student__school_class")
            .order_by("student__last_name", "student__first_name"))


def room_history(room, limit: int = 30) -> QuerySet[DormStay]:
    return room.stays.filter(checked_out__isnull=False).select_related("student").order_by("-checked_out")[:limit]


def check_in_candidates(room) -> QuerySet:
    """Joylashtirish ro'yxati: shu filialdagi faol, hozir yotoqxonada yashamaydigan, jinsi mos o'quvchilar."""
    qs = (Student.objects.filter(branch=room.branch, status=Student.Status.ACTIVE)
          # Exists: qaydi umuman yo'q o'quvchi ham qolsin (JOIN'dagi NULL "yashayapti" deb tushunilmasin)
          .exclude(Exists(DormStay.objects.filter(student=OuterRef("pk"), checked_out__isnull=True)))
          .select_related("school_class")
          .order_by("last_name", "first_name"))
    if room.gender == DormRoom.Gender.MALE:
        qs = qs.filter(gender="M")
    elif room.gender == DormRoom.Gender.FEMALE:
        qs = qs.filter(gender="F")
    return qs


# ---------- Davomat ----------

WEEKDAYS_SHORT = ["Du", "Se", "Cho", "Pa", "Ju", "Sha", "Ya"]
ATTENDANCE_DAYS = 20   # sukut: oxirgi 20 kun
MAX_DAYS = 62


@dataclass(frozen=True)
class AttendanceFilters:
    q: str = ""
    gender: str = ""
    room: int | None = None
    school_class: int | None = None
    date_from: date | None = None
    date_to: date | None = None


def attendance_period(f: AttendanceFilters, today: date) -> tuple[date, date]:
    end = min(f.date_to or today, today)
    start = f.date_from or end - timedelta(days=ATTENDANCE_DAYS - 1)
    start = max(min(start, end), end - timedelta(days=MAX_DAYS - 1))
    return start, end


def attendance_stays(branch, f: AttendanceFilters, start: date, end: date) -> QuerySet[DormStay]:
    """Davr ichida yashagan qaydlar (filtr bilan)."""
    qs = (DormStay.objects.filter(room__branch=branch, checked_in__lte=end)
          .filter(Q(checked_out__isnull=True) | Q(checked_out__gte=start))
          .select_related("student", "room"))
    if f.room:
        qs = qs.filter(room_id=f.room)
    if f.gender:
        qs = qs.filter(student__gender=f.gender)
    if f.school_class:
        qs = qs.filter(student__school_class_id=f.school_class)
    for term in f.q.split()[:5]:
        qs = qs.filter(Q(student__last_name__icontains=term) | Q(student__first_name__icontains=term)
                       | Q(student__code__icontains=term))
    return qs.order_by("room__name", "student__last_name", "student__first_name", "-checked_in")


def attendance_students(stays) -> list[dict]:
    """Qaydlarni o'quvchi bo'yicha birlashtiradi (bir davrda ikki xonada yashagan bo'lsa ham bitta qator)."""
    rows: dict[int, dict] = {}
    for stay in stays:
        row = rows.setdefault(stay.student_id, {"student": stay.student, "stay": stay, "stays": []})
        row["stays"].append(stay)
        if stay.checked_in > row["stay"].checked_in:
            row["stay"] = stay
    return list(rows.values())


def attendance_days(start: date, end: date, today: date) -> list[dict]:
    days, d = [], start
    while d <= end:
        days.append({"date": d, "label": WEEKDAYS_SHORT[d.weekday()], "weekend": d.weekday() >= 5,
                     "today": d == today})
        d += timedelta(days=1)
    return days


def fill_attendance_rows(rows: list[dict], days: list[dict]) -> list[dict]:
    """Sahifadagi qatorlarga kataklar va jamilar (bitta so'rov)."""
    if not rows or not days:
        return rows
    marks = {(a.student_id, a.date): a.status for a in DormAttendance.objects.filter(
        student_id__in=[r["student"].pk for r in rows], date__range=(days[0]["date"], days[-1]["date"]))}
    for row in rows:
        totals = dict.fromkeys(DormAttendance.Status.values, 0)
        cells = []
        for d in days:
            active = any(s.checked_in <= d["date"] and (s.checked_out is None or s.checked_out >= d["date"])
                         for s in row["stays"])
            status = marks.get((row["student"].pk, d["date"]), "")
            if status:
                totals[status] += 1
            cells.append({"date": d["date"], "status": status, "active": active})
        row["cells"], row["totals"] = cells, totals
    return rows


def attendance_today(branch, today: date) -> dict:
    """Statistika: hozir yashayotganlar va bugungi belgilar."""
    stays = DormStay.objects.filter(room__branch=branch, checked_in__lte=today, checked_out__isnull=True)
    s = stays.aggregate(total=Count("id"), male=Count("id", filter=Q(student__gender="M")),
                        female=Count("id", filter=Q(student__gender="F")))
    marks = DormAttendance.objects.filter(stay__in=stays, date=today)
    s["present"] = marks.filter(status__in=[DormAttendance.Status.PRESENT, DormAttendance.Status.LATE]).count()
    s["absent"] = marks.filter(status__in=[DormAttendance.Status.ABSENT, DormAttendance.Status.EXCUSED]).count()
    s["unmarked"] = s["total"] - marks.count()
    return s


def day_sheet(branch, day: date, room: int | None = None) -> list[dict]:
    """«Kunlik belgilash»: o'sha kuni yashagan o'quvchilar va ularning belgisi."""
    stays = (DormStay.objects.filter(room__branch=branch, checked_in__lte=day)
             .filter(Q(checked_out__isnull=True) | Q(checked_out__gte=day)).select_related("student", "room"))
    if room:
        stays = stays.filter(room_id=room)
    marks = dict(DormAttendance.objects.filter(stay__in=stays, date=day).values_list("student_id", "status"))
    return [{"stay": s, "status": marks.get(s.student_id, "")}
            for s in stays.order_by("room__name", "student__last_name", "student__first_name")]
