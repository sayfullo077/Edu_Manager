from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import CodeSequence
from apps.common.storage import PrivateStorage
from apps.core.models import AcademicYear, Branch, TimeStampedModel
from apps.people.models import Guardian, Student

from .validators import validate_pdf


def scan_upload_to(instance, filename):
    # Asl fayl nomi ishlatilmaydi (path traversal va shaxsiy ma'lumot sizishiga qarshi).
    return f"contracts/{instance.academic_year_id}/{instance.number}.pdf"


class ContractTemplate(TimeStampedModel):
    """Shartnoma matni shabloni. Matnda o'rinbosarlar ({{ vasiy }}, {{ oquvchi }} ...) va oddiy belgilash:
    `# ` sarlavha, `## ` bo'lim, `### ` kichik sarlavha, `>> ` o'ngga, `- ` ro'yxat, `**qalin**`
    (to'liq ro'yxat — `contracts.domain.document`). Imzolangan shartnoma matni muhrlanadi — shablon keyin
    o'zgarsa ham imzolangan nusxa o'zgarmaydi."""

    name = models.CharField("nomi", max_length=120, unique=True)
    body = models.TextField("matn")
    is_active = models.BooleanField("faol", default=True)
    is_default = models.BooleanField("sukut bo'yicha", default=False)

    class Meta:
        verbose_name = "shartnoma shabloni"
        verbose_name_plural = "shartnoma shablonlari"
        ordering = ["-is_default", "name"]

    def __str__(self):
        return self.name


class Contract(TimeStampedModel):
    """O'quvchi va maktab o'rtasidagi shartnoma.

    Hayot sikli: qoralama → yuborilgan (ota-onaga SMS kod) → imzolangan. Istalgan bosqichda bekor qilinishi mumkin.
    Qog'ozdagi nusxa imzolanadi, skaneri PDF sifatida biriktiriladi.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Qoralama"
        SENT = "sent", "Yuborilgan"
        SIGNED = "signed", "Imzolangan"
        CANCELLED = "cancelled", "Bekor qilingan"

    number = models.CharField("raqami", max_length=20, unique=True, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="contracts", verbose_name="filial")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="contracts",
                                      verbose_name="o'quv yili")
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="contracts", verbose_name="o'quvchi")
    guardian = models.ForeignKey(Guardian, on_delete=models.PROTECT, related_name="contracts",
                                 verbose_name="shartnoma tomoni (ota-ona)")
    class_name = models.CharField("sinf", max_length=40, blank=True,
                                  help_text="Shartnoma tuzilgan paytdagi sinf (keyin o'zgarsa ham saqlanadi)")
    full_tariff = models.DecimalField("to'liq tarif (oyiga)", max_digits=12, decimal_places=2,
                                      validators=[MinValueValidator(Decimal("1"))])
    discount_percent = models.DecimalField("chegirma (%)", max_digits=5, decimal_places=2, default=Decimal("0"),
                                           validators=[MinValueValidator(0), MaxValueValidator(100)])
    discount_reason = models.CharField("chegirma sababi", max_length=160, blank=True)
    monthly_fee = models.DecimalField("oylik to'lov", max_digits=12, decimal_places=2, editable=False)
    start_date = models.DateField("boshlanish sanasi")
    end_date = models.DateField("tugash sanasi")
    status = models.CharField("holati", max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    sent_at = models.DateTimeField("yuborilgan", null=True, blank=True)
    signed_at = models.DateTimeField("imzolangan", null=True, blank=True)
    signed_phone = models.CharField("tasdiqlagan telefon", max_length=12, blank=True)
    cancelled_at = models.DateTimeField("bekor qilingan", null=True, blank=True)
    cancel_reason = models.CharField("bekor qilish sababi", max_length=255, blank=True)
    scan = models.FileField("skaner (PDF)", upload_to=scan_upload_to, storage=PrivateStorage(), blank=True,
                            validators=[FileExtensionValidator(["pdf"]), validate_pdf])
    notes = models.TextField("izoh", blank=True)
    template = models.ForeignKey(ContractTemplate, on_delete=models.PROTECT, null=True, blank=True,
                                 related_name="contracts", verbose_name="shablon")
    # Imzolangan paytdagi matn va ma'lumotlar (muhr): keyin shablon yoki rekvizit o'zgarsa ham o'zgarmaydi
    signed_body = models.TextField("imzolangan matn", blank=True, editable=False)
    signed_data = models.JSONField("imzolangan ma'lumotlar", default=dict, blank=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+",
                                   verbose_name="tuzgan xodim")

    class Meta:
        verbose_name = "shartnoma"
        verbose_name_plural = "shartnomalar"
        ordering = ["-created_at"]
        constraints = [
            # Bir o'quvchiga bir o'quv yilida faqat bitta amaldagi shartnoma.
            models.UniqueConstraint(fields=["student", "academic_year"],
                                    condition=~models.Q(status="cancelled"),
                                    name="one_active_contract_per_student_year"),
            models.CheckConstraint(condition=models.Q(end_date__gt=models.F("start_date")),
                                   name="contract_dates_order"),
        ]
        indexes = [models.Index(fields=["branch", "status"])]

    def __str__(self):
        return self.number

    @staticmethod
    def calc_monthly_fee(full_tariff: Decimal, discount_percent: Decimal) -> Decimal:
        fee = Decimal(full_tariff) * (Decimal(100) - Decimal(discount_percent)) / Decimal(100)
        return fee.quantize(Decimal("1"), rounding=ROUND_HALF_UP)  # so'mgacha yaxlitlanadi

    def save(self, *args, **kwargs):
        self.monthly_fee = self.calc_monthly_fee(self.full_tariff, self.discount_percent)
        if not self.number:
            self.number = CodeSequence.next_code("CTR", self.start_date.year)
        super().save(*args, **kwargs)

    @property
    def otp_subject(self) -> str:
        return f"contract:{self.pk}"

    @property
    def is_editable(self) -> bool:
        return self.status == self.Status.DRAFT

    @property
    def months(self) -> int:
        """Shartnoma qamrab olgan oylar soni (sentyabr–iyun = 10)."""
        return (self.end_date.year - self.start_date.year) * 12 + self.end_date.month - self.start_date.month + 1

    @property
    def total_amount(self) -> Decimal:
        return self.monthly_fee * self.months
