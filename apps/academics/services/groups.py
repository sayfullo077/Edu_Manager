"""Guruhlar: yaratish/tahrirlash (fanlar va o'qituvchilar bilan), tanlov guruhi a'zolari.

- Butun sinf guruhi — a'zolar sinfdan olinadi, alohida yozilmaydi.
- Tanlov guruhi — `GroupMembership`. Chiqarilgan o'quvchi o'chirilmaydi: `left_at` qo'yiladi (oylik hisob-kitobi
  o'tgan oylar uchun kim guruhda bo'lganini bilishi kerak). Qayta qo'shilsa — shu yozuv tiklanadi.
"""

import logging
from dataclasses import dataclass
from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.people.models import Student, Teacher

from .. import selectors
from ..models import Group, GroupMembership, GroupSubject, Subject
from . import timetable

logger = logging.getLogger(__name__)

FIELDS = ("school_class", "code", "kind", "level", "pay_scheme", "rate", "deduction_percent", "room", "capacity",
          "is_active")


@dataclass(frozen=True)
class SubjectTeacher:
    subject: Subject
    teacher: Teacher
    hours: int = 0  # haftalik soat (jadvaldagi limit), 0 — belgilanmagan


def _validate(g: Group, subjects: list[SubjectTeacher]) -> None:
    errors = {}
    g.code = "".join((g.code or "").split()).upper()
    if g.school_class.branch_id != g.branch_id:
        errors["school_class"] = "Sinf boshqa filialga tegishli."
    if g.room and g.room.branch_id != g.branch_id:
        errors["room"] = "Xona boshqa filialga tegishli."
    if g.rate is not None and g.rate <= 0:
        errors["rate"] = "Stavka musbat bo'lishi kerak."
    if g.pay_scheme == Group.PayScheme.PER_LESSON and g.deduction_percent:
        errors["deduction_percent"] = "Ushlanma faqat o'quvchi boshiga (belgilangan summa) sxemasida qo'llanadi."
    if not subjects:
        errors["__all__"] = "Kamida bitta fan va uning o'qituvchisini tanlang."
    seen = set()
    for st in subjects:
        if st.subject.pk in seen:
            errors["__all__"] = f"«{st.subject.name}» fani ikki marta tanlangan."
        seen.add(st.subject.pk)
        if st.teacher.branch_id != g.branch_id or st.teacher.status in Teacher.NOT_WORKING:
            errors["__all__"] = f"{st.teacher} — shu filialning faol o'qituvchisi emas."
    if g.pk and g.kind == Group.Kind.SUBSET:
        n = g.memberships.filter(left_at__isnull=True).count()
        if g.capacity < n:
            errors["capacity"] = f"Guruhda {n} nafar o'quvchi bor — sig'im undan kam bo'lmasin."
    if errors:
        raise ValidationError(errors)


def save_group(instance: Group | None, *, branch, by, subjects: list[SubjectTeacher], **data) -> Group:
    g = instance or Group(branch=branch)
    if instance and "kind" in data and data["kind"] != instance.kind and \
            instance.memberships.filter(left_at__isnull=True).exists():
        raise ValidationError({"kind": "Guruhda a'zolar bor — turini o'zgartirishdan oldin ularni chiqaring."})
    for field in FIELDS:
        if field in data:
            setattr(g, field, data[field])
    if instance and g.school_class_id != instance.__class__.objects.get(pk=g.pk).school_class_id \
            and g.lessons.filter(valid_to__isnull=True).exists():
        raise ValidationError({"school_class": "Guruhning jadvalda darslari bor — sinfini o'zgartirib bo'lmaydi."})
    g.academic_year_id = g.school_class.academic_year_id  # guruh sinfining o'quv yiliga tegishli
    _validate(g, subjects)
    today = date.today()
    old = {gs.subject_id: gs.teacher_id for gs in g.subjects.all()} if instance else {}
    new = {st.subject.pk: st.teacher for st in subjects}
    removed = [sid for sid in old if sid not in new
               and timetable.open_lessons_for_subject(g, sid, today).exists()]
    if removed:
        names = ", ".join(Subject.objects.filter(pk__in=removed).values_list("name", flat=True))
        raise ValidationError(f"«{names}» fanining jadvalda darslari bor — avval Dars jadvalidan olib tashlang.")
    try:
        with transaction.atomic():
            g.save()
            g.subjects.all().delete()
            GroupSubject.objects.bulk_create(GroupSubject(group=g, subject=st.subject, teacher=st.teacher,
                                                          hours_per_week=st.hours) for st in subjects)
            for st in subjects:  # o'qituvchi almashgan fanlar — darslar bugundan yangi o'qituvchiga
                if old.get(st.subject.pk) not in (None, st.teacher.pk):
                    timetable.move_teacher(group=g, subject=st.subject, teacher=st.teacher, on=today, by=by)
    except IntegrityError as e:
        raise ValidationError({"code": f"«{g.code}» kodli guruh bu o'quv yilida bor."}) from e
    logger.info("Guruh %s: %s (user=%s)", "tahrirlandi" if instance else "yaratildi", g.code, by.pk)
    return g


@transaction.atomic
def add_members(group: Group, *, students: list[Student], on: date, by) -> int:
    if group.kind != Group.Kind.SUBSET:
        raise ValidationError("Butun sinf guruhining o'quvchilari sinfdan olinadi — alohida qo'shilmaydi.")
    group = Group.objects.select_for_update().get(pk=group.pk)
    current = group.memberships.filter(left_at__isnull=True).count()
    if current + len(students) > group.capacity:
        raise ValidationError(f"Sig'im yetmaydi: {group.capacity} o'rindan {current} tasi band.")
    busy = set(selectors.subject_busy_students(group).values_list("student_id", flat=True))
    added = 0
    for s in students:
        if s.branch_id != group.branch_id or s.status != Student.Status.ACTIVE:
            raise ValidationError(f"{s.short_name} — shu filialning faol o'quvchisi emas.")
        if s.pk in busy:
            raise ValidationError(f"{s.short_name} bu fan bo'yicha boshqa guruhda o'qiydi — avval o'sha guruhdan "
                                  "chiqarilishi kerak.")
        m, created = GroupMembership.objects.get_or_create(group=group, student=s, defaults={"joined_at": on})
        if not created:
            if m.left_at is None:
                continue  # allaqachon a'zo
            m.joined_at, m.left_at = on, None  # qayta qo'shildi
            m.save(update_fields=["joined_at", "left_at"])
        added += 1
    logger.info("Guruh %s: %d o'quvchi qo'shildi (user=%s)", group.code, added, by.pk)
    return added


def remove_member(membership: GroupMembership, *, on: date, by) -> None:
    if membership.left_at:
        return
    if on < membership.joined_at:
        raise ValidationError("Chiqish sanasi qo'shilgan sanadan oldin bo'lishi mumkin emas.")
    membership.left_at = on
    membership.save(update_fields=["left_at"])
    logger.info("Guruhdan chiqarildi: %s ← %s (user=%s)", membership.group.code, membership.student.code, by.pk)


def delete_group(group: Group, *, by) -> str:
    """A'zolik tarixi bor guruh o'chirilmaydi — faolsizlantiriladi. Qaytaradi: "deleted" | "deactivated"."""
    if group.memberships.exists():
        group.is_active = False
        group.save(update_fields=["is_active", "updated_at"])
        logger.info("Guruh faolsizlantirildi: %s (user=%s)", group.code, by.pk)
        return "deactivated"
    group.delete()
    logger.info("Guruh o'chirildi: %s (user=%s)", group.code, by.pk)
    return "deleted"
