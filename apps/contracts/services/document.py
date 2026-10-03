"""Shartnoma hujjati: shablon + shartnoma/maktab ma'lumotlari. Imzolanganda matn va qiymatlar muhrlanadi."""

import logging

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.common.templatetags.ui import money, phone
from apps.core.models import SchoolSettings

from ..domain.document import render_blocks, unknown_placeholders
from ..models import Contract, ContractTemplate

logger = logging.getLogger(__name__)

DATE = "%d.%m.%Y"


def default_template() -> ContractTemplate | None:
    return (ContractTemplate.objects.filter(is_active=True).order_by("-is_default", "name").first())


def document_data(contract: Contract) -> dict:
    """Shablon o'rinbosarlari uchun joriy qiymatlar (imzolanguncha "tirik")."""
    school = SchoolSettings.load()
    branch, student, guardian = contract.branch, contract.student, contract.guardian
    grade = student.grade or (student.school_class.grade if student.school_class else None)
    return {
        "raqam": contract.number, "sana": contract.created_at.strftime(DATE) if contract.created_at else "",
        "oquv_yili": contract.academic_year.name,
        "maktab": school.name, "yuridik_nomi": school.legal_name or f"«{school.name}»",
        "filial": branch.name, "filial_manzili": branch.address, "direktor": branch.director_name,
        "maktab_telefon": phone(branch.phone) if branch.phone else "", "bank_hisob": branch.bank_account,
        "bank_nomi": branch.bank_name, "mfo": branch.bank_mfo, "stir": branch.inn,
        "vasiy": guardian.full_name, "vasiy_telefon": phone(guardian.phone),
        "oquvchi": student.full_name, "oquvchi_kodi": student.code,
        "sinf": contract.class_name, "sinf_darajasi": f"{grade}-sinf" if grade else contract.class_name,
        "boshlanish": contract.start_date.strftime(DATE), "tugash": contract.end_date.strftime(DATE),
        "tarif": money(contract.full_tariff),
        "chegirma": f"{contract.discount_percent.normalize():f}%" if contract.discount_percent else "0%",
        "oylik_tolov": money(contract.monthly_fee), "oylar": str(contract.months),
        "jami": money(contract.total_amount),
    }


def contract_document(contract: Contract) -> dict:
    """Ko'rsatish/chop etish uchun: bloklar, rekvizitlar ma'lumoti, muhrlanganmi."""
    if contract.signed_body:
        body, data, sealed = contract.signed_body, contract.signed_data, True
    else:
        template = contract.template or default_template()
        body, data, sealed = (template.body if template else ""), document_data(contract), False
    return {"blocks": render_blocks(body, data), "data": data, "sealed": sealed,
            "template_name": contract.template.name if contract.template else ""}


def seal(contract: Contract) -> None:
    """Imzolash paytida: joriy shablon matni va qiymatlar shartnomaga yoziladi (keyin o'zgarmaydi)."""
    template = contract.template or default_template()
    Contract.objects.filter(pk=contract.pk).update(
        signed_body=template.body if template else "", signed_data=document_data(contract),
        template=template)


# ---------- Shablonlar ----------

def save_template(instance: ContractTemplate | None, *, by, name: str, body: str, is_active: bool,
                  is_default: bool) -> ContractTemplate:
    unknown = unknown_placeholders(body)
    if unknown:
        raise ValidationError({"body": "Noma'lum o'rinbosar: " + ", ".join(f"{{{{ {k} }}}}" for k in unknown)})
    if is_default and not is_active:
        raise ValidationError({"is_default": "Sukut shablon faol bo'lishi kerak."})
    t = instance or ContractTemplate()
    t.name, t.body, t.is_active, t.is_default = name.strip(), body, is_active, is_default
    if ContractTemplate.objects.filter(name__iexact=t.name).exclude(pk=t.pk).exists():
        raise ValidationError({"name": "Bunday nomli shablon bor."})
    with transaction.atomic():
        if is_default:
            ContractTemplate.objects.exclude(pk=t.pk).update(is_default=False)
        t.save()
    logger.info("Shartnoma shabloni %s: %s (user=%s)", "tahrirlandi" if instance else "yaratildi", t.name, by.pk)
    return t
