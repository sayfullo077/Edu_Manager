from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.core.models import Branch, TimeStampedModel

from .domain.phone import format_phone, normalize_phone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, phone, password, **extra):
        user = self.model(phone=normalize_phone(phone), **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, phone, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(phone, password, **extra)

    def create_superuser(self, phone, password=None, **extra):
        extra["is_staff"] = True
        extra["is_superuser"] = True
        return self._create_user(phone, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """Tizim foydalanuvchisi. Ro'yxatdan o'tish yo'q: akkauntlarni admin yaratadi."""

    phone = models.CharField("telefon (login)", max_length=12, unique=True)
    last_name = models.CharField("familiya", max_length=60)
    first_name = models.CharField("ism", max_length=60)
    middle_name = models.CharField("otasining ismi", max_length=60, blank=True)
    avatar = models.ImageField("rasm", upload_to="avatars/", blank=True)
    is_active = models.BooleanField("faol", default=True)
    is_staff = models.BooleanField("admin panelga kirish", default=False)
    date_joined = models.DateTimeField("qo'shilgan", default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["last_name", "first_name"]

    class Meta:
        verbose_name = "foydalanuvchi"
        verbose_name_plural = "foydalanuvchilar"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return " ".join(p for p in [self.last_name, self.first_name, self.middle_name] if p)

    @property
    def short_name(self):
        return f"{self.last_name} {self.first_name}".strip()

    @property
    def initials(self):
        return f"{self.last_name[:1]}{self.first_name[:1]}".upper()

    @property
    def phone_display(self):
        return format_phone(self.phone)

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.first_name


class Role(models.TextChoices):
    TEACHER = "teacher", "O'qituvchi"
    HEAD_TEACHER = "head_teacher", "Zavuch"
    RECEPTION = "reception", "Qabul | Reception"
    DIRECTOR = "director", "Direktor"


# Rol almashtirgichdagi tartib: Direktor → Reception → Zavuch → O'qituvchi (asl tizimdagidek).
ROLE_ORDER = {Role.DIRECTOR: 0, Role.RECEPTION: 1, Role.HEAD_TEACHER: 2, Role.TEACHER: 3}


class UserRole(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="roles")
    role = models.CharField("rol", max_length=20, choices=Role.choices)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="user_roles")
    is_active = models.BooleanField("faol", default=True)

    class Meta:
        verbose_name = "foydalanuvchi roli"
        verbose_name_plural = "foydalanuvchi rollari"
        constraints = [
            models.UniqueConstraint(fields=["user", "role", "branch"], name="unique_user_role_branch"),
        ]

    def __str__(self):
        return f"{self.user.short_name} — {self.get_role_display()} ({self.branch})"


class OneTimeCode(models.Model):
    """SMS orqali yuborilgan bir martalik kod. Kodning o'zi emas, faqat hash saqlanadi."""

    class Purpose(models.TextChoices):
        LOGIN = "login", "Tizimga kirish"
        CONTRACT = "contract", "Shartnomani tasdiqlash"

    class Channel(models.TextChoices):
        SMS = "sms", "SMS"
        TELEGRAM = "telegram", "Telegram"

    phone = models.CharField(max_length=12, db_index=True)
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.SMS)
    subject = models.CharField(max_length=40, blank=True, default="",
                               help_text="Kod qaysi obyekt uchun, masalan: contract:15")
    code_hash = models.CharField(max_length=128)
    attempts = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["phone", "purpose", "-created_at"])]

    def __str__(self):
        return f"{self.phone} ({self.purpose})"


class TelegramLink(models.Model):
    """Foydalanuvchining Telegram chati. Bot faqat /start bosgan odamga yoza oladi,
    shuning uchun xodim botga bir marta o'z raqamini ulashadi."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="telegram")
    chat_id = models.BigIntegerField("chat ID", unique=True)
    username = models.CharField("Telegram username", max_length=64, blank=True)
    linked_at = models.DateTimeField("ulangan", auto_now_add=True)

    class Meta:
        verbose_name = "Telegram ulanishi"
        verbose_name_plural = "Telegram ulanishlari"

    def __str__(self):
        return f"{self.user.short_name} → {self.chat_id}"


class ImpersonationLog(models.Model):
    """Superadmin kim/qaysi rol qiyofasida qachon ishlaganining audit jurnali (o'chirilmaydi)."""

    class Mode(models.TextChoices):
        ROLE = "role", "Rol sifatida ko'rish"
        USER = "user", "Foydalanuvchi sifatida kirish"

    actor = models.ForeignKey(User, on_delete=models.PROTECT, related_name="impersonations_made",
                              verbose_name="superadmin")
    mode = models.CharField("rejim", max_length=10, choices=Mode.choices)
    target = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True,
                               related_name="impersonations_received", verbose_name="kim sifatida")
    role = models.CharField("rol", max_length=20, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, null=True, blank=True, verbose_name="filial")
    ip = models.GenericIPAddressField("IP", null=True, blank=True)
    started_at = models.DateTimeField("boshlangan", auto_now_add=True)
    ended_at = models.DateTimeField("tugagan", null=True, blank=True)
    actions = models.PositiveIntegerField("o'zgartirish so'rovlari", default=0)

    class Meta:
        verbose_name = "impersonation jurnali"
        verbose_name_plural = "impersonation jurnali"
        ordering = ["-started_at"]

    def __str__(self):
        who = self.target.short_name if self.target else self.role
        return f"{self.actor.short_name} → {who} ({self.started_at:%d.%m.%Y %H:%M})"
