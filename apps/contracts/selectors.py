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
    return (Contract.objects.select_related("student__school_class", "guardian", "academic_year", "created_by")
            .get(branch=branch, pk=pk))


def active_contract_for(student) -> Contract | None:
    return (student.contracts.exclude(status=Contract.Status.CANCELLED)
            .select_related("academic_year").order_by("-created_at").first())
