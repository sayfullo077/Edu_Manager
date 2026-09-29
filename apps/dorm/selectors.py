"""Yotoqxona o'qish so'rovlari."""

from dataclasses import dataclass
from datetime import date

from django.db.models import Count, Exists, OuterRef, Q, QuerySet, Sum

from apps.people.models import Student

from .models import DormRoom, DormStay

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
