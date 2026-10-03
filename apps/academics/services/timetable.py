"""Dars jadvali: qo'ng'iroqlar, dars qo'shish/olib tashlash, o'qituvchi almashishi. Tarix saqlanadi.

Asosiy qoidalar:
- Dars `valid_from`–`valid_to` oralig'ida amal qiladi. O'zgarish "qaysi sanadan" bilan kiritiladi: eski yozuv
  shu sanadan bir kun oldin yopiladi, yangisi shu sanadan ochiladi. Hali boshlanmagan dars (sana ≤ valid_from)
  olib tashlansa — butunlay o'chiriladi (bo'sh tarix qoldirmaslik uchun).
- Qat'iy taqiq (bir vaqtda — bir hafta kuni va bir dars raqami, amal qilish davrlari kesishsa):
  guruh, o'qituvchi, xona, butun sinf (ikki "butun sinf" darsi) va o'quvchi (ikki guruh a'zolari kesishsa).
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from apps.people.models import Student

from ..models import Group, GroupMembership, Lesson, Room, Subject, TimeSlot

logger = logging.getLogger(__name__)

DEFAULT_STARTS = ("08:30", "09:25", "10:20", "11:20", "12:15", "13:05", "14:00", "14:55")
DEFAULT_MINUTES = 50


# ---------- Qo'ng'iroqlar ----------

def ensure_slots(branch) -> list[TimeSlot]:
    """Filialda dars vaqtlari bo'lmasa — sukut (8 ta dars, 50 daqiqa) yaratiladi."""
    slots = list(TimeSlot.objects.filter(branch=branch).order_by("number"))
    if slots:
        return slots
    for n, start in enumerate(DEFAULT_STARTS, start=1):
        s = datetime.strptime(start, "%H:%M")
        TimeSlot.objects.create(branch=branch, number=n, start=s.time(),
                                end=(s + timedelta(minutes=DEFAULT_MINUTES)).time())
    return list(TimeSlot.objects.filter(branch=branch).order_by("number"))


@dataclass(frozen=True)
class SlotRow:
    number: int
    start: time | None
    end: time | None
    is_break: bool = False


def save_slots(branch, rows: list[SlotRow], *, by) -> None:
    """Qo'ng'iroqlarni saqlash. Bo'sh qator — o'sha dars vaqti olib tashlanadi (darsi bo'lmasa)."""
    filled = [r for r in rows if r.start or r.end]
    errors = []
    for r in filled:
        if not (r.start and r.end):
            errors.append(f"{r.number}-dars: boshlanish va tugash vaqtini kiriting.")
        elif r.end <= r.start:
            errors.append(f"{r.number}-dars: tugash vaqti boshlanishdan keyin bo'lsin.")
    ordered = sorted((r for r in filled if r.start and r.end), key=lambda r: r.number)
    for a, b in zip(ordered, ordered[1:], strict=False):
        if b.start < a.end:
            errors.append(f"{b.number}-dars {a.number}-dars tugashidan oldin boshlanyapti.")
    keep = {r.number for r in filled}
    used = set(TimeSlot.objects.filter(branch=branch, lessons__isnull=False).exclude(number__in=keep)
               .values_list("number", flat=True))
    for n in sorted(used):
        errors.append(f"{n}-dars vaqtini olib tashlab bo'lmaydi — jadvalda darslari bor.")
    breaks = {r.number for r in filled if r.is_break}
    for n in sorted(set(TimeSlot.objects.filter(branch=branch, number__in=breaks, is_break=False,
                                               lessons__valid_to__isnull=True).values_list("number", flat=True))):
        errors.append(f"{n}-dars vaqtida darslar bor — tanaffus qilishdan oldin ularni ko'chiring.")
    if errors:
        raise ValidationError(errors)
    with transaction.atomic():
        TimeSlot.objects.filter(branch=branch).exclude(number__in=keep).delete()
        for r in ordered:
            TimeSlot.objects.update_or_create(branch=branch, number=r.number,
                                              defaults={"start": r.start, "end": r.end, "is_break": r.is_break})
    logger.info("Qo'ng'iroqlar yangilandi: %d ta dars (user=%s)", len(ordered), by.pk)


# ---------- Ziddiyatlar ----------

def _members(group: Group) -> set[int]:
    if group.kind == Group.Kind.WHOLE_CLASS:
        return set(Student.objects.filter(school_class=group.school_class_id, status=Student.Status.ACTIVE)
                   .values_list("pk", flat=True))
    return set(GroupMembership.objects.filter(group=group, left_at__isnull=True,
                                              student__status=Student.Status.ACTIVE)
               .values_list("student_id", flat=True))


def _describe(lesson: Lesson) -> str:
    return (f"{lesson.group.code} · {lesson.subject.name} ({lesson.get_weekday_display()}, "
            f"{lesson.slot.number}-dars, {lesson.valid_from:%d.%m.%Y} dan)")


def conflicts(*, group: Group, teacher, weekday: int, slot: TimeSlot, room: Room | None, start: date,
              end: date | None = None, exclude_pk: int | None = None) -> list[str]:
    """Shu vaqtda (kun + dars raqami) va kesishgan davrda band bo'lganlar — xato matnlari ro'yxati."""
    overlap = Q(valid_to__isnull=True) | Q(valid_to__gte=start)
    if end:
        overlap &= Q(valid_from__lte=end)
    others = (Lesson.objects.filter(overlap, branch=group.branch_id, weekday=weekday, slot=slot)
              .exclude(pk=exclude_pk).select_related("group__school_class", "subject", "teacher__user", "slot",
                                                     "room"))
    problems, members = [], None
    for other in others:
        if other.group_id == group.pk:
            problems.append(f"Guruh bu vaqtda darsda: {_describe(other)}.")
            continue
        if other.teacher_id == teacher.pk:
            problems.append(f"O'qituvchi {teacher.user.short_name} bu vaqtda band: {_describe(other)}.")
        if room and other.room_id == room.pk:
            problems.append(f"«{room.name}» xonasi bu vaqtda band: {_describe(other)}.")
        if (group.kind == other.group.kind == Group.Kind.WHOLE_CLASS
                and other.group.school_class_id == group.school_class_id):
            problems.append(f"«{group.school_class.name}» sinfi bu vaqtda darsda: {_describe(other)}.")
            continue
        members = _members(group) if members is None else members
        common = members & _members(other.group)
        if common:
            problems.append(f"{len(common)} nafar o'quvchi bir vaqtda ikki guruhda bo'lib qoladi: {_describe(other)}.")
    return problems


# ---------- Darslar ----------

def _check_period(group: Group, on: date) -> None:
    year = group.academic_year
    if not (year.start_date <= on <= year.end_date):
        raise ValidationError({"on": f"Sana {year.name} o'quv yili ichida bo'lsin "
                                     f"({year.start_date:%d.%m.%Y} — {year.end_date:%d.%m.%Y})."})


def add_lesson(*, group: Group, subject: Subject, weekday: int, slot: TimeSlot, room: Room | None, on: date,
               by) -> Lesson:
    if not group.is_active:
        raise ValidationError({"group": "Guruh faol emas."})
    gs = group.subjects.select_related("teacher__user").filter(subject=subject).first()
    if gs is None:
        raise ValidationError({"subject": "Bu fan guruhga biriktirilmagan."})
    if slot.branch_id != group.branch_id or (room and room.branch_id != group.branch_id):
        raise ValidationError("Dars vaqti yoki xona boshqa filialga tegishli.")
    if slot.is_break:
        raise ValidationError(f"{slot.start:%H:%M}–{slot.end:%H:%M} — tanaffus (obed), dars qo'yilmaydi.")
    _check_period(group, on)
    with transaction.atomic():
        TimeSlot.objects.select_for_update().get(pk=slot.pk)  # bir vaqtdagi ikki so'rov ziddiyatni chetlab o'tmasin
        problems = conflicts(group=group, teacher=gs.teacher, weekday=weekday, slot=slot, room=room, start=on)
        if problems:
            raise ValidationError(problems)
        lesson = Lesson.objects.create(
            branch_id=group.branch_id, academic_year_id=group.academic_year_id, group=group, subject=subject,
            teacher=gs.teacher, weekday=weekday, slot=slot, room=room, valid_from=on, created_by=by)
    logger.info("Dars qo'shildi: %s (user=%s)", lesson, by.pk)
    return lesson


def remove_lesson(lesson: Lesson, *, on: date, by) -> str:
    """`on` sanasidan boshlab dars yo'q. Qaytaradi: "deleted" (hali boshlanmagan edi) | "closed"."""
    if lesson.valid_to is not None and lesson.valid_to < on:
        raise ValidationError("Bu dars allaqachon yopilgan.")
    if on <= lesson.valid_from:
        lesson.delete()
        logger.info("Dars o'chirildi (boshlanmagan): %s (user=%s)", lesson, by.pk)
        return "deleted"
    lesson.valid_to = on - timedelta(days=1)
    lesson.save(update_fields=["valid_to", "updated_at"])
    logger.info("Dars yopildi %s dan: %s (user=%s)", on, lesson, by.pk)
    return "closed"


def move_teacher(*, group: Group, subject: Subject, teacher, on: date, by) -> int:
    """Guruhda fan o'qituvchisi almashdi: `on` dan boshlab ochiq darslar yangi o'qituvchiga o'tadi.

    Boshlangan dars bo'linadi (eskisi `on - 1` da yopiladi, yangisi `on` dan ochiladi). Yangi o'qituvchi shu vaqtda
    band bo'lsa — xato (hech narsa o'zgarmaydi).
    """
    open_lessons = list(Lesson.objects.filter(Q(valid_to__isnull=True) | Q(valid_to__gte=on), group=group,
                                              subject=subject).exclude(teacher=teacher).select_related("slot", "room"))
    for lesson in open_lessons:
        problems = [p for p in conflicts(group=group, teacher=teacher, weekday=lesson.weekday, slot=lesson.slot,
                                         room=None, start=max(on, lesson.valid_from), end=lesson.valid_to,
                                         exclude_pk=lesson.pk) if p.startswith("O'qituvchi")]
        if problems:
            raise ValidationError(problems)
    for lesson in open_lessons:
        if lesson.valid_from >= on:
            lesson.teacher = teacher
            lesson.save(update_fields=["teacher", "updated_at"])
            continue
        old_end, lesson.valid_to = lesson.valid_to, on - timedelta(days=1)
        lesson.save(update_fields=["valid_to", "updated_at"])
        Lesson.objects.create(branch_id=lesson.branch_id, academic_year_id=lesson.academic_year_id, group=group,
                              subject=subject, teacher=teacher, weekday=lesson.weekday, slot=lesson.slot,
                              room=lesson.room, valid_from=on, valid_to=old_end, created_by=by)
    if open_lessons:
        logger.info("O'qituvchi almashdi: %s · %s, %d dars (user=%s)", group.code, subject, len(open_lessons), by.pk)
    return len(open_lessons)


def open_lessons_for_subject(group: Group, subject_id: int, on: date):
    return Lesson.objects.filter(Q(valid_to__isnull=True) | Q(valid_to__gte=on), group=group, subject_id=subject_id)


def default_room(group: Group) -> Room | None:
    """Guruh xonasi, bo'lmasa sinf xonasi."""
    return group.room or group.school_class.room


@transaction.atomic
def place_card(*, groups: list[Group], subject: Subject, weekday: int, slot: TimeSlot, on: date, by) -> list[Lesson]:
    """Jadvalga kartani joylash (sudrab qo'yish). "Hovuz" — bir fan bir nechta guruhda (sinf bo'lingan):
    hamma guruh darsi bir vaqtda qo'yiladi. Biror guruhda ziddiyat bo'lsa — hech biri qo'yilmaydi."""
    lessons = []
    for group in groups:
        try:
            lessons.append(add_lesson(group=group, subject=subject, weekday=weekday, slot=slot,
                                      room=default_room(group), on=on, by=by))
        except ValidationError as e:
            prefix = f"{group.code}: " if len(groups) > 1 else ""
            raise ValidationError([prefix + m for m in e.messages]) from e
    return lessons


@transaction.atomic
def move_lesson(lesson: Lesson, *, weekday: int, slot: TimeSlot, on: date, by) -> Lesson:
    """Darsni boshqa katakka ko'chirish (`on` sanasidan): eskisi yopiladi, yangisi ochiladi — bitta tranzaksiyada.
    Ziddiyat bo'lsa hech narsa o'zgarmaydi."""
    if lesson.weekday == weekday and lesson.slot_id == slot.pk:
        return lesson
    group, subject, room = lesson.group, lesson.subject, lesson.room
    on = max(on, lesson.valid_from)
    remove_lesson(lesson, on=on, by=by)
    return add_lesson(group=group, subject=subject, weekday=weekday, slot=slot, room=room, on=on, by=by)
