"""Yotoqxona: xonalar va o'quvchilarning yashash qaydlari.

- Bitta o'quvchi bir vaqtda faqat bitta xonada yashaydi (chiqmagan qayd — bitta).
- Qaydlar o'chirilmaydi: chiqqanda `checked_out` qo'yiladi — tarix saqlanadi (to'lov va davomat shunga tayanadi).
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import Branch, TimeStampedModel


class DormRoom(TimeStampedModel):
    class Gender(models.TextChoices):
        MALE = "male", "O'g'il"
        FEMALE = "female", "Qiz"
        MIXED = "mixed", "Aralash"

    class Status(models.TextChoices):
        ACTIVE = "active", "Faol"
        INACTIVE = "inactive", "Nofaol"
        REPAIR = "repair", "Ta'mirda"

    class RoomType(models.IntegerChoices):
        """Xona turi — bitta bo'limdagi karavotlar (2/4/6/8 o'rinli). Umumiy sig'im (`capacity`) alohida."""
        TWO = 2, "2 o'rinli"
        FOUR = 4, "4 o'rinli"
        SIX = 6, "6 o'rinli"
        EIGHT = 8, "8 o'rinli"

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="dorm_rooms", verbose_name="filial")
    name = models.CharField("nomi (raqami)", max_length=60, help_text="Masalan: 29-xona")
    floor = models.CharField("qavat", max_length=30, blank=True, help_text="Masalan: 1-qavat")
    room_type = models.PositiveSmallIntegerField("xona turi", choices=RoomType.choices, default=RoomType.TWO)
    gender = models.CharField("jinsi", max_length=6, choices=Gender.choices)
    capacity = models.PositiveSmallIntegerField("sig'im (o'rinlar)", validators=[MinValueValidator(1)])
    status = models.CharField("holati", max_length=8, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    monthly_fee = models.DecimalField("oylik to'lov", max_digits=12, decimal_places=2, default=Decimal("0"),
                                      help_text="Yotoqxona to'lovi (grafik uchun)")
    notes = models.CharField("izoh", max_length=255, blank=True)

    class Meta:
        verbose_name = "yotoqxona xonasi"
        verbose_name_plural = "yotoqxona xonalari"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["branch", "name"], name="unique_dorm_room_name")]

    def __str__(self):
        return self.name

    @property
    def free(self) -> int:
        """Bo'sh o'rinlar. Selector `occupied` ni annotatsiya qiladi — bo'lmasa bazadan sanaydi."""
        occupied = getattr(self, "occupied", None)
        if occupied is None:
            occupied = self.stays.filter(checked_out__isnull=True).count()
        return max(self.capacity - occupied, 0)

    def accepts(self, student_gender: str) -> bool:
        """Xona o'quvchi jinsiga mosmi (Student.gender: "M"/"F")."""
        return (self.gender == self.Gender.MIXED
                or (self.gender == self.Gender.MALE and student_gender == "M")
                or (self.gender == self.Gender.FEMALE and student_gender == "F"))


class DormStay(TimeStampedModel):
    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="dorm_stays",
                                verbose_name="o'quvchi")
    room = models.ForeignKey(DormRoom, on_delete=models.PROTECT, related_name="stays", verbose_name="xona")
    checked_in = models.DateField("kirgan sana")
    checked_out = models.DateField("chiqqan sana", null=True, blank=True)
    monthly_fee = models.DecimalField("oylik to'lov", max_digits=12, decimal_places=2,
                                      help_text="Shu o'quvchi uchun (xona narxidan kam bo'lsa — farq chegirma)")
    note = models.CharField("izoh", max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        verbose_name = "yotoqxonada yashash"
        verbose_name_plural = "yotoqxonada yashash qaydlari"
        ordering = ["-checked_in"]
        constraints = [
            models.UniqueConstraint(fields=["student"], condition=models.Q(checked_out__isnull=True),
                                    name="one_active_dorm_stay"),
            models.CheckConstraint(condition=models.Q(checked_out__isnull=True)
                                   | models.Q(checked_out__gte=models.F("checked_in")), name="dorm_stay_dates"),
        ]
        indexes = [models.Index(fields=["room", "checked_out"])]

    def __str__(self):
        return f"{self.student} → {self.room}"
