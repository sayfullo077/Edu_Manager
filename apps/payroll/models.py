from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import Branch, TimeStampedModel

MONEY = {"max_digits": 14, "decimal_places": 2}
PERCENT = {"max_digits": 5, "decimal_places": 2, "default": Decimal("0"),
           "validators": [MinValueValidator(0), MaxValueValidator(100)]}


class PayrollSettings(TimeStampedModel):
    """Filial bo'yicha ustama foizlari va sinf rahbarlik summasi (Zavuch «Sozlamalar» oynasida o'zgartiradi)."""

    branch = models.OneToOneField(Branch, on_delete=models.CASCADE, related_name="payroll_settings")
    first_category_percent = models.DecimalField("1-toifa ustamasi (%)", **PERCENT)
    second_category_percent = models.DecimalField("2-toifa ustamasi (%)", **{**PERCENT, "default": Decimal("10")})
    specialist_category_percent = models.DecimalField("Mutaxassis ustamasi (%)", **PERCENT)
    highest_category_percent = models.DecimalField("Oliy toifa ustamasi (%)", **PERCENT)
    certificate_percent = models.DecimalField("sertifikat ustamasi (%)", **{**PERCENT, "default": Decimal("30")},
                                              help_text="Sertifikat fanidan tushgan asosiy oylikka")
    language_percent = models.DecimalField("til ustamasi (%)", **{**PERCENT, "default": Decimal("15")},
                                           help_text="Rus / ingliz tilidagi sinflar darslaridan tushgan qismga")
    homeroom_rate = models.DecimalField("sinf rahbarlik (so'm, o'quvchi boshiga)", **MONEY, default=Decimal("30000"),
                                        validators=[MinValueValidator(0)],
                                        help_text="Har o'quvchi uchun: stavka × to'lagan / to'liq tarif")

    class Meta:
        verbose_name = "oylik sozlamalari"
        verbose_name_plural = "oylik sozlamalari"

    def __str__(self):
        return f"Oylik sozlamalari · {self.branch}"

    def category_percent(self, category: str) -> Decimal:
        return getattr(self, f"{category}_category_percent", Decimal("0")) if category else Decimal("0")


class Penalty(TimeStampedModel):
    """Qo'lda kiritilgan jarima. O'chirilmaydi — bekor qilinadi (kim, qachon, nega)."""

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="penalties")
    teacher = models.ForeignKey("people.Teacher", on_delete=models.PROTECT, related_name="penalties",
                                verbose_name="o'qituvchi")
    month = models.DateField("oy", help_text="Oyning 1-sanasi")
    amount = models.DecimalField("summa", **MONEY, validators=[MinValueValidator(Decimal("1"))])
    reason = models.CharField("sababi", max_length=255)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    cancelled_at = models.DateTimeField("bekor qilingan", null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name="+")
    cancel_reason = models.CharField("bekor qilish sababi", max_length=255, blank=True)

    class Meta:
        verbose_name = "jarima"
        verbose_name_plural = "jarimalar"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.teacher} · {self.month:%Y-%m} · {self.amount}"

    @property
    def is_active(self) -> bool:
        return self.cancelled_at is None


class SalaryPayment(TimeStampedModel):
    """O'qituvchiga berilgan pul (avans yoki oylik). Kassa/bankdan chiqim — `finance.Expense` orqali."""

    class Kind(models.TextChoices):
        ADVANCE = "advance", "Avans"
        SALARY = "salary", "Oylik"

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="salary_payments")
    teacher = models.ForeignKey("people.Teacher", on_delete=models.PROTECT, related_name="salary_payments",
                                verbose_name="o'qituvchi")
    month = models.DateField("qaysi oy uchun", help_text="Oyning 1-sanasi")
    kind = models.CharField("turi", max_length=10, choices=Kind.choices)
    amount = models.DecimalField("summa", **MONEY, validators=[MinValueValidator(Decimal("1"))])
    paid_on = models.DateField("berilgan sana")
    expense = models.OneToOneField("finance.Expense", on_delete=models.PROTECT, related_name="salary_payment")
    note = models.CharField("izoh", max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        verbose_name = "oylik to'lovi"
        verbose_name_plural = "oylik to'lovlari"
        ordering = ["-paid_on", "-created_at"]
        indexes = [models.Index(fields=["branch", "month"])]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.teacher} · {self.amount}"
