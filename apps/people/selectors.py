"""O'qish so'rovlari: ro'yxatlar, statistika. Har doim filial bilan cheklangan."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import Count, Exists, OuterRef, Prefetch, Q, QuerySet

from apps.academics.models import Group, SchoolClass
from apps.common import crypto
from apps.contracts.models import Contract
from apps.core.models import AcademicYear
from apps.finance.models import Withdrawal

from .models import Guardian, Student, StudentGuardian


@dataclass(frozen=True)
class StudentFilters:
    q: str = ""
    status: str = ""
    school_class: int | None = None
    gender: str = ""
    academic_year: int | None = None
    grade: int | None = None
    tariff: Decimal | None = None
    joined_from: date | None = None
    joined_to: date | None = None
    in_erp: bool | None = None
    in_emaktab: bool | None = None


def students(branch, filters: StudentFilters) -> QuerySet[Student]:
    qs = Student.objects.filter(branch=branch).select_related("school_class")
    if filters.status:
        qs = qs.filter(status=filters.status)
    if filters.school_class:
        qs = qs.filter(school_class_id=filters.school_class)
    if filters.gender:
        qs = qs.filter(gender=filters.gender)
    if filters.academic_year:
        qs = qs.filter(school_class__academic_year_id=filters.academic_year)
    if filters.grade:
        qs = qs.filter(grade=filters.grade)
    if filters.tariff is not None:
        qs = qs.filter(Exists(Contract.objects.filter(student=OuterRef("pk"), full_tariff=filters.tariff)
                              .exclude(status=Contract.Status.CANCELLED)))
    if filters.joined_from:
        qs = qs.filter(joined_at__gte=filters.joined_from)
    if filters.joined_to:
        qs = qs.filter(joined_at__lte=filters.joined_to)
    if filters.in_erp is not None:
        qs = qs.filter(in_erp=filters.in_erp)
    if filters.in_emaktab is not None:
        qs = qs.filter(in_emaktab=filters.in_emaktab)
    # Har bir so'z ism, familiya, otasining ismi, kod yoki telefonda bo'lishi kerak.
    for term in filters.q.split()[:5]:
        digits = "".join(ch for ch in term if ch.isdigit())
        cond = (Q(last_name__icontains=term) | Q(first_name__icontains=term) |
                Q(middle_name__icontains=term) | Q(code__icontains=term))
        if len(digits) >= 3:
            cond |= Q(phone__contains=digits)
        qs = qs.filter(cond)
    return qs.order_by("last_name", "first_name")


def student_stats(branch) -> dict:
    """Bitta SQL so'rovda barcha kartalar uchun raqamlar."""
    month_start = date.today().replace(day=1)
    return Student.objects.filter(branch=branch).aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(status=Student.Status.ACTIVE)),
        graduated=Count("id", filter=Q(status=Student.Status.GRADUATED)),
        joined_this_month=Count("id", filter=Q(joined_at__gte=month_start)),
    )


def tariff_choices(branch) -> list[Decimal]:
    """Filialdagi amaldagi shartnomalarda uchraydigan to'liq tariflar (filtr uchun)."""
    return list(Contract.objects.filter(branch=branch).exclude(status=Contract.Status.CANCELLED)
                .order_by("full_tariff").values_list("full_tariff", flat=True).distinct())


def student_has_history(student: Student) -> bool:
    """Shartnoma, hisob yoki to'lov bo'lsa o'quvchi o'chirilmaydi (moliya yozuvlari saqlanadi)."""
    return (student.contracts.exists() or student.invoices.exists() or student.payments.exists())


def needs_settlement(student: Student) -> bool:
    """Pul bilan bog'liq ochiq hisob bor (grafik yoki to'lov), lekin chiqish hisob-kitobi hali qilinmagan."""
    if Withdrawal.objects.filter(student_id=student.pk).exists():
        return False
    return (student.payments.exists()
            or student.invoices.exclude(status="cancelled").exists())


def class_choices(branch, *, all_years: bool = False) -> QuerySet[SchoolClass]:
    """Sinflar. Sukut bo'yicha joriy o'quv yili; `all_years` — tahrirlash formasi uchun (yil tanlanadi)."""
    qs = SchoolClass.objects.filter(branch=branch, is_active=True).select_related("academic_year")
    year = AcademicYear.current()
    if year and not all_years:
        qs = qs.filter(academic_year=year)
    return qs.order_by("-academic_year__start_date", "kind", "grade", "name")


def address_suggestions(branch) -> dict[str, list[str]]:
    """Tuman va mahalla uchun takliflar — shu filialda avval kiritilgan qiymatlar."""
    students = Student.objects.filter(branch=branch)
    return {field: list(students.exclude(**{field: ""}).order_by(field).values_list(field, flat=True)
                        .distinct()[:300])
            for field in ("district", "mahalla")}


def student_edit(branch, pk: int) -> Student:
    """Tahrirlash sahifasi: vasiylar va har bir vasiyning nechta farzandi borligi (umumiy yozuv ogohlantirishi)."""
    links = (StudentGuardian.objects.select_related("guardian")
             .annotate(children_total=Count("guardian__child_links"))
             .order_by("-is_primary", "relation"))
    return (Student.objects.select_related("school_class__academic_year", "branch")
            .prefetch_related(Prefetch("guardian_links", queryset=links))
            .get(branch=branch, pk=pk))


def student_detail(branch, pk: int) -> Student:
    return (Student.objects
            .select_related("school_class__academic_year", "branch")
            .prefetch_related(Prefetch("guardian_links",
                                       queryset=StudentGuardian.objects.select_related("guardian")
                                       .order_by("-is_primary", "relation")),
                              Prefetch("groups", queryset=Group.objects.select_related("school_class")
                                       .prefetch_related("subjects__subject", "subjects__teacher__user")))
            .get(branch=branch, pk=pk))


def student_siblings(student: Student) -> QuerySet[Student]:
    """Aka-uka / opa-singillar: shu filialda umumiy ota-onasi (vasiysi) bor boshqa o'quvchilar."""
    guardian_ids = [link.guardian_id for link in student.guardian_links.all()]
    return (Student.objects.filter(branch=student.branch_id, guardian_links__guardian_id__in=guardian_ids)
            .exclude(pk=student.pk).select_related("school_class").distinct().order_by("-birth_date"))


def student_contracts(student: Student) -> QuerySet[Contract]:
    return student.contracts.select_related("academic_year").order_by("-created_at")


# ---------- Ota-onalar ----------

PINFL_RE = re.compile(r"^\d{14}$")
PASSPORT_RE = re.compile(r"^[A-Z]{2}\d{7}$")


def guardians(branch, q: str = "", relation: str = "", status: str = "") -> QuerySet[Guardian]:
    """Filialdagi o'quvchilarning ota-onalari. JSHSHIR/passport faqat to'liq kiritilsa topiladi (shifrlangan)."""
    qs = (Guardian.objects.filter(child_links__student__branch=branch)
          .annotate(children_count=Count("child_links", filter=Q(child_links__student__branch=branch),
                                         distinct=True),
                    relations=ArrayAgg("child_links__relation", distinct=True))
          .distinct())
    if relation:
        qs = qs.filter(child_links__relation=relation)
    if status:
        qs = qs.filter(status=status)
    compact = "".join(q.split()).upper()
    if PINFL_RE.match(compact):
        return qs.filter(pinfl_index=crypto.blind_index(compact))
    if PASSPORT_RE.match(compact):
        return qs.filter(passport_index=crypto.blind_index(compact))
    for term in q.split()[:5]:
        digits = "".join(ch for ch in term if ch.isdigit())
        cond = Q(last_name__icontains=term) | Q(first_name__icontains=term) | Q(middle_name__icontains=term)
        if len(digits) >= 3:
            cond |= Q(phone__contains=digits) | Q(extra_phone__contains=digits)
        qs = qs.filter(cond)
    return qs.order_by("last_name", "first_name")


def guardian_stats(branch) -> dict:
    links = StudentGuardian.objects.filter(student__branch=branch)
    month_start = date.today().replace(day=1)
    return {
        "total": links.values("guardian").distinct().count(),
        "fathers": links.filter(relation=StudentGuardian.Relation.FATHER).values("guardian").distinct().count(),
        "mothers": links.filter(relation=StudentGuardian.Relation.MOTHER).values("guardian").distinct().count(),
        # "Boshqa vasiylar" — ota va onadan tashqari hamma (buva, buvi, tog'a, xola, boshqa)
        "others": links.exclude(relation__in=[StudentGuardian.Relation.FATHER, StudentGuardian.Relation.MOTHER])
                       .values("guardian").distinct().count(),
        "new_this_month": links.filter(guardian__created_at__date__gte=month_start)
                               .values("guardian").distinct().count(),
    }


def guardian_detail(branch, pk: int) -> Guardian:
    return (Guardian.objects.filter(child_links__student__branch=branch).distinct()
            .prefetch_related(Prefetch("child_links",
                                       queryset=StudentGuardian.objects.filter(student__branch=branch)
                                       .select_related("student__school_class", "student__branch")
                                       .order_by("student__last_name", "student__first_name")))
            .get(pk=pk))


def find_existing_guardian(*, pinfl: str = "", phone: str = "", last_name: str = "") -> Guardian | None:
    """Takrorlanishga qarshi: avval JSHSHIR (ishonchli), keyin telefon + familiya."""
    if pinfl:
        found = Guardian.objects.filter(pinfl_index=crypto.blind_index(pinfl)).first()
        if found:
            return found
    if phone and last_name:
        return Guardian.objects.filter(phone=phone, last_name__iexact=last_name).first()
    return None
