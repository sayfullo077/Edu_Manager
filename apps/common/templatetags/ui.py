import os
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

from apps.accounts.domain.phone import format_phone

register = template.Library()

AVATAR_TONES = 6


@register.filter
def phone(value):
    """998901234567 → +998 90 123 45 67"""
    return format_phone(value) if value else "—"


@register.filter
def money(value):
    """1750000 → 1 750 000 (bo'shliq — ingichka bo'lmagan probel, qatorga bo'linmaydi)."""
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    return f"{number:,.0f}".replace(",", " ")


@register.filter
def short_money(value):
    """Kartalar uchun qisqa summa: 474 312 000 → "474.3 mln", 1 250 000 000 → "1.3 mlrd". To'liq qiymat — title'da."""
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    sign, n = ("-" if number < 0 else ""), abs(number)
    for limit, unit in ((Decimal(10) ** 9, "mlrd"), (Decimal(10) ** 6, "mln")):
        if n >= limit:
            return f"{sign}{(n / limit).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)} {unit}".replace(".0 ", " ")
    return f"{sign}{n:,.0f}".replace(",", " ")


@register.simple_tag
def static_v(path):
    """Kesh muammosiga qarshi: dev'da fayl o'zgarsa URL ham o'zgaradi (?v=<mtime>), brauzer eski JS/CSS'ni
    ishlatmaydi. Prod'da ManifestStaticFilesStorage nomga hash qo'shadi — qo'shimcha parametr kerak emas."""
    url = static(path)
    if settings.DEBUG and (found := finders.find(path)):
        url = f"{url}?v={int(os.path.getmtime(found))}"
    return url


@register.filter
def class_short(name):
    """Avatar doirasiga sig'adigan sinf nomi: "2-B", "Aniq2" — o'zgarmaydi; "Ijtimoiy1" → "Ijt1"."""
    name = str(name or "")
    if len(name) <= 5:
        return name
    head = name.rstrip("0123456789")
    return head[:3] + name[len(head):]


@register.filter
def tone(value):
    """Avatar uchun barqaror rang: bir odam har doim bir xil rangda."""
    return sum(map(ord, str(value))) % AVATAR_TONES


@register.simple_tag
def page_url(querystring, number):
    return f"?{querystring}&page={number}" if querystring else f"?page={number}"


@register.filter
def flags(student):
    """ERP / E-maktab belgilari jadval ustunlari uchun: [(maydon, qiymat), ...]."""
    return [("in_erp", student.in_erp), ("in_emaktab", student.in_emaktab)]


@register.filter
def relation_label(value):
    from apps.people.models import StudentGuardian
    return StudentGuardian.Relation(value).label if value in StudentGuardian.Relation.values else value


@register.filter
def mask(value, visible=4):
    """Shaxsiy raqamlarni ekranda yashirish: 31510724140053 → ••••••••••0053 (yelkadan qarashga qarshi)."""
    if not value:
        return ""
    value = str(value)
    return "•" * max(0, len(value) - visible) + value[-visible:]


SEGMENTS = {1: "seg-success", 2: "seg-info", 3: "seg-amber", 4: "seg-danger"}


@register.filter
def seg_class(index):
    return SEGMENTS.get(index, "seg-info")


@register.filter
def clamp100(value):
    try:
        return max(0, min(100, float(value)))
    except (TypeError, ValueError):
        return 0


@register.filter
def budget_groups(budget):
    return [("Doimiy xarajatlar", "oy sayin bir xil limit", budget["fixed"]),
            ("Normativ xarajatlar", "o'zgaruvchan limit", budget["normative"])]


@register.inclusion_tag("partials/bar.html")
def bar(percent, tone=""):
    """CSP'ga mos progress chiziq: kenglik SVG atributi (inline style emas)."""
    return {"percent": clamp100(percent), "tone": tone}


@register.filter
def invoice_state(invoice):
    """Ko'rsatish uchun holat: muddati o'tgan to'lanmagan oy — 'overdue'."""
    from django.utils import timezone
    if invoice.status in ("pending", "partial") and invoice.due_date < timezone.localdate():
        return "overdue"
    return invoice.status


@register.filter
def paid_count(invoices):
    return sum(1 for i in invoices if i.status == "paid")


@register.filter
def role_label(value):
    from apps.accounts.models import Role
    return Role(value).label if value in Role.values else value


@register.filter
def tojson(value):
    """data-* atributi uchun JSON (autoescape qo'shtirnoqlarni xavfsiz qiladi)."""
    import json
    return json.dumps(value, ensure_ascii=False, default=str)


ROLE_ICONS = {"reception": "building", "head_teacher": "building", "teacher": "book", "director": "shield"}


@register.filter
def role_icon(role):
    return ROLE_ICONS.get(role, "users")


@register.filter
def branch_count(roles):
    return len({r.branch_id for r in roles})
