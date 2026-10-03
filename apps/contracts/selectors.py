from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from .models import Contract


def contracts(branch, *, q: str = "", status: str = "", academic_year: int | None = None,
              school_class: int | None = None) -> QuerySet[Contract]:
    qs = Contract.objects.filter(branch=branch).select_related("student__school_class", "guardian", "academic_year")
    if status == "expired":  # imzolangan, lekin tugash sanasi o'tib ketgan
        qs = qs.filter(status=Contract.Status.SIGNED, end_date__lt=timezone.localdate())
    elif status:
        qs = qs.filter(status=status)
    if academic_year:
        qs = qs.filter(academic_year_id=academic_year)
    if school_class:
        qs = qs.filter(student__school_class_id=school_class)
    for term in q.split()[:5]:
        qs = qs.filter(Q(number__icontains=term) | Q(student__last_name__icontains=term) |
                       Q(student__first_name__icontains=term) | Q(student__code__icontains=term))
    return qs.order_by("-created_at")


def contract_stats(branch) -> dict:
    return Contract.objects.filter(branch=branch).aggregate(
        total=Count("id", filter=~Q(status=Contract.Status.CANCELLED)),
        draft=Count("id", filter=Q(status=Contract.Status.DRAFT)),
        sent=Count("id", filter=Q(status=Contract.Status.SENT)),
        signed=Count("id", filter=Q(status=Contract.Status.SIGNED)),
    )


def contract_detail(branch, pk: int) -> Contract:
    return (Contract.objects.select_related("student__school_class", "guardian", "academic_year", "created_by",
                                           "branch", "template")
            .get(branch=branch, pk=pk))


def active_contract_for(student) -> Contract | None:
    return (student.contracts.exclude(status=Contract.Status.CANCELLED)
            .select_related("academic_year").order_by("-created_at").first())


def contract_candidates(branch, year):
    """Yangi shartnoma uchun: faol o'quvchilar, shu o'quv yilida amaldagi shartnomasi yo'q."""
    from apps.people.models import Student
    taken = Contract.objects.filter(academic_year=year).exclude(status=Contract.Status.CANCELLED).values("student")
    return (Student.objects.filter(branch=branch, status=Student.Status.ACTIVE).exclude(pk__in=taken)
            .select_related("school_class").prefetch_related("guardian_links__guardian")
            .order_by("last_name", "first_name"))


def candidate_map(students) -> dict:
    """JS uchun: {o'quvchi_id: {tarif, sinf, vasiylar: [[id, "F.I.Sh. · Ota", asosiymi], ...]}}."""
    result = {}
    for s in students:
        links = sorted(s.guardian_links.all(), key=lambda link: not link.is_primary)
        result[s.pk] = {
            "tariff": int(s.school_class.monthly_tariff) if s.school_class else None,
            "class": s.school_class.name if s.school_class else "",
            "guardians": [[link.guardian_id, f"{link.guardian.full_name} · {link.get_relation_display()}",
                           link.is_primary] for link in links],
        }
    return result
