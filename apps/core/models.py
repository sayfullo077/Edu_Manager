from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("yaratilgan", auto_now_add=True)
    updated_at = models.DateTimeField("yangilangan", auto_now=True)

    class Meta:
        abstract = True


class SchoolSettings(TimeStampedModel):
    """Maktab brendi: nom, logo, asosiy rang. Bazada bitta yozuv bo'ladi."""

    name = models.CharField("maktab nomi", max_length=120, default="Maktab")
    short_name = models.CharField("qisqa nom", max_length=40, default="Maktab")
    tagline = models.CharField("shior", max_length=160, blank=True)
    logo = models.ImageField("logo", upload_to="branding/", blank=True)
    # Qiymat <style> ichiga yoziladi — faqat qat'iy HEX formatga ruxsat (CSS injection bo'lmasin).
    brand_color = models.CharField("asosiy rang (HEX)", max_length=7, default="#08915E",
                                   validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Masalan: #08915E")])

    CACHE_KEY = "school_settings:v1"
    CACHE_TTL = 60 * 60

    class Meta:
        verbose_name = "maktab sozlamalari"
        verbose_name_plural = "maktab sozlamalari"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.full_clean(exclude=["logo"])
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(self.CACHE_KEY)

    @classmethod
    def load(cls):
        """Har bir sahifada kerak bo'ladi — bazaga har safar bormaslik uchun keshlanadi."""
        obj = cache.get(cls.CACHE_KEY)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(cls.CACHE_KEY, obj, cls.CACHE_TTL)
        return obj


class Branch(TimeStampedModel):
    name = models.CharField("nomi", max_length=120, unique=True)
    address = models.CharField("manzil", max_length=255, blank=True)
    phone = models.CharField("telefon", max_length=20, blank=True)
    is_active = models.BooleanField("faol", default=True)

    class Meta:
        verbose_name = "filial"
        verbose_name_plural = "filiallar"
        ordering = ["name"]

    def __str__(self):
        return self.name


class AcademicYear(TimeStampedModel):
    name = models.CharField("nomi", max_length=20, unique=True, help_text="Masalan: 2026-2027")
    start_date = models.DateField("boshlanishi")
    end_date = models.DateField("tugashi")
    is_current = models.BooleanField("joriy", default=False)

    class Meta:
        verbose_name = "o'quv yili"
        verbose_name_plural = "o'quv yillari"
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_current"],
                condition=models.Q(is_current=True),
                name="only_one_current_academic_year",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError("Boshlanish sanasi tugash sanasidan oldin bo'lishi kerak.")

    @classmethod
    def current(cls):
        return cls.objects.filter(is_current=True).first()
