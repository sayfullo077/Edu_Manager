"""O'qituvchilar (HR): qo'shish/tahrirlash (foydalanuvchi, rol, sertifikatlar bilan) va holatni o'zgartirish."""

import logging
import secrets
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Role, User, UserRole

from ..models import Certificate, Teacher

logger = logging.getLogger(__name__)


def set_status(teacher: Teacher, *, status: str, by) -> Teacher:
    """Nofaol yoki Bo'shatilgan holatga o'tkazishdan oldin: jadvalda ochiq darslari va guruhlari bo'lmasligi kerak
    (aks holda darslar egasiz qoladi — oylik va jadval buziladi)."""
    if status not in Teacher.Status.values:
        raise ValidationError("Noto'g'ri holat.")
    if status in Teacher.NOT_WORKING and teacher.status not in Teacher.NOT_WORKING:
        today = timezone.localdate()
        lessons = teacher.lessons.filter(Q(valid_to__isnull=True) | Q(valid_to__gte=today)).count()
        groups = teacher.group_subjects.filter(group__is_active=True).count()
        if lessons or groups:
            raise ValidationError(
                f"{teacher.user.short_name}da {groups} ta guruh fani va {lessons} ta dars bor — avval «Sinflar va "
                "guruhlar»da boshqa o'qituvchiga o'tkazing (darslar jadvalda avtomatik o'tadi).")
    old, teacher.status = teacher.status, status
    teacher.save(update_fields=["status", "updated_at"])
    logger.info("O'qituvchi holati: %s %s → %s (user=%s)", teacher.code, old, status, by.pk)
    return teacher


TEACHER_FIELDS = ("kind", "status", "category", "birth_date", "gender", "marital_status", "email", "passport",
                  "pinfl", "card_number", "address", "official_employment", "fixed_salary", "education", "specialty",
                  "experience_years", "teaching_languages", "hired_at", "contract_start", "contract_end", "notes")
CERT_FIELDS = ("kind", "subject", "number", "issued_on", "expires_on", "score", "issued_by")


@dataclass(frozen=True)
class CertificateData:
    pk: int | None
    delete: bool
    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SaveResult:
    teacher: Teacher
    temp_password: str | None  # faqat yangi foydalanuvchi yaratilganda — bir marta ko'rsatiladi


def _temp_password() -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"  # chalkash belgilarsiz (0/O, 1/l)
    return "".join(secrets.choice(alphabet) for _ in range(10))


def save_teacher(instance: Teacher | None, *, branch, by, user_data: dict, teacher_data: dict, subjects,
                 certificates: list[CertificateData]) -> SaveResult:
    """Qo'shish yoki tahrirlash. Telefon — login: boshqa foydalanuvchida bo'lsa xato; o'qituvchi profili yo'q mavjud
    foydalanuvchi (masalan, Reception xodimi) bo'lsa — unga bog'lanadi. Yangi foydalanuvchiga tasodifiy vaqtinchalik
    parol beriladi (telefon raqami parol qilinmaydi — xavfsiz emas)."""
    phone = user_data["phone"]
    temp_password = None
    with transaction.atomic():
        if instance:
            user = instance.user
            if User.objects.filter(phone=phone).exclude(pk=user.pk).exists():
                raise ValidationError({"phone": "Bu telefon boshqa foydalanuvchiga tegishli."})
        else:
            user = User.objects.filter(phone=phone).first()
            if user and Teacher.objects.filter(user=user).exists():
                raise ValidationError({"phone": "Bu telefon bilan o'qituvchi allaqachon bor."})
            if user is None:
                temp_password = _temp_password()
                user = User.objects.create_user(phone, temp_password, last_name=user_data["last_name"],
                                                first_name=user_data["first_name"])
        for name in ("last_name", "first_name", "middle_name", "phone"):
            setattr(user, name, user_data.get(name, getattr(user, name)) or "")
        user.save()
        teacher = instance or Teacher(user=user, branch=branch)
        for name in TEACHER_FIELDS:
            if name in teacher_data:
                setattr(teacher, name, teacher_data[name])
        teacher.full_clean(exclude=["user", "subjects"])
        teacher.save()
        teacher.subjects.set(subjects)
        UserRole.objects.get_or_create(user=user, role=Role.TEACHER, branch=branch)
        _save_certificates(teacher, certificates)
    logger.info("O'qituvchi %s: %s (user=%s)", "tahrirlandi" if instance else "qo'shildi", teacher.code, by.pk)
    return SaveResult(teacher=teacher, temp_password=temp_password)


def _save_certificates(teacher: Teacher, items: list[CertificateData]) -> None:
    existing = {c.pk: c for c in teacher.certificates.all()}
    for item in items:
        cert = existing.get(item.pk) if item.pk else None
        if item.delete:
            if cert:
                cert.delete()
            continue
        cert = cert or Certificate(teacher=teacher)
        for name in CERT_FIELDS:
            setattr(cert, name, item.data.get(name))
        cert.number, cert.issued_by = cert.number or "", cert.issued_by or ""
        if cert.expires_on and cert.issued_on and cert.expires_on < cert.issued_on:
            raise ValidationError("Sertifikat: tugash sanasi boshlanishdan oldin bo'lishi mumkin emas.")
        cert.save()
