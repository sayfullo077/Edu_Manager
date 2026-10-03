from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import AcademicYear, Branch, TimeStampedModel


class Language(models.TextChoices):
    UZ = "uz", "O'zbek"
    RU = "ru", "Rus"
    EN = "en", "Ingliz"


class Subject(TimeStampedModel):
    """Fan. Bir xil fan turli tilda alohida yozuv: "Matematika" (uz) va "Математика" (ru)."""

    name = models.CharField("nomi", max_length=120)
    language = models.CharField("o'qitish tili", max_length=2, choices=Language.choices, default=Language.UZ)
    is_active = models.BooleanField("faol", default=True)

    class Meta:
        verbose_name = "fan"
        verbose_name_plural = "fanlar"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["name", "language"], name="unique_subject_language")]

    def __str__(self):
        return self.name


class Room(TimeStampedModel):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="rooms", verbose_name="filial")
    name = models.CharField("nomi", max_length=40, help_text="Masalan: 31-xona")
    capacity = models.PositiveSmallIntegerField("sig'imi", default=30)
    is_active = models.BooleanField("faol", default=True)

    class Meta:
        verbose_name = "xona"
        verbose_name_plural = "xonalar"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["branch", "name"], name="unique_room_branch")]

    def __str__(self):
        return self.name


class SchoolClass(TimeStampedModel):
    """Sinf: oddiy ("3-B") yoki yo'nalish ("Aniq1", "Ijtimoiy2" — bir necha sinf o'quvchilari aralash)."""

    class Kind(models.TextChoices):
        REGULAR = "regular", "Oddiy sinf"
        DIRECTION = "direction", "Yo'nalish"

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="classes", verbose_name="filial")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="classes",
                                      verbose_name="o'quv yili")
    name = models.CharField("nomi", max_length=40)
    kind = models.CharField("turi", max_length=10, choices=Kind.choices, default=Kind.REGULAR)
    grade = models.PositiveSmallIntegerField("sinf (daraja)", null=True, blank=True,
                                             validators=[MinValueValidator(1), MaxValueValidator(11)],
                                             help_text="Yo'nalishlar uchun bo'sh qoldiriladi")
    language = models.CharField("ta'lim tili", max_length=2, choices=Language.choices, default=Language.UZ)
    homeroom_teacher = models.ForeignKey("people.Teacher", on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name="homeroom_classes", verbose_name="sinf rahbari")
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="xona")
    capacity = models.PositiveSmallIntegerField("sig'imi", default=30)
    monthly_tariff = models.DecimalField("oylik to'lov (tarif)", max_digits=12, decimal_places=2,
                                         default=Decimal("1750000"),
                                         help_text="Chegirmasiz to'liq narx. Shartnoma tuzishda sukut bo'yicha olinadi")
    is_active = models.BooleanField("faol", default=True)

    class Meta:
        verbose_name = "sinf"
        verbose_name_plural = "sinflar"
        ordering = ["grade", "name"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "academic_year", "name"], name="unique_class_per_year"),
        ]

    def __str__(self):
        return self.name


class Group(TimeStampedModel):
    """O'qitish guruhi — oylik shu birlik bo'yicha hisoblanadi.

    - Butun sinf (4-A → IT): `kind=whole_class`, o'quvchilar sinfdan olinadi, stavka darsbay.
    - Tanlov guruhi (IT+PHYS-Aniq1-01): `kind=subset`, o'quvchilar alohida biriktiriladi, stavka o'quvchibay.
    """

    class Kind(models.TextChoices):
        WHOLE_CLASS = "whole_class", "Butun sinf"
        SUBSET = "subset", "Tanlov guruhi"

    class PayScheme(models.TextChoices):
        PER_LESSON = "per_lesson", "Darsbay (dars × stavka)"
        PER_STUDENT = "per_student", "Belgilangan summa (o'quvchi boshiga)"

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="groups", verbose_name="filial")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="groups",
                                      verbose_name="o'quv yili")
    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, related_name="groups",
                                     verbose_name="sinf")
    code = models.CharField("kodi", max_length=60, help_text="Masalan: IT+PHYS-Aniq1-01")
    kind = models.CharField("turi", max_length=12, choices=Kind.choices, default=Kind.WHOLE_CLASS)
    level = models.CharField("daraja", max_length=60, blank=True, help_text="Masalan: 2-darajali fanlarga")
    pay_scheme = models.CharField("to'lov sxemasi", max_length=12, choices=PayScheme.choices,
                                  default=PayScheme.PER_LESSON)
    rate = models.DecimalField("stavka (so'm)", max_digits=12, decimal_places=2, default=Decimal("2400"),
                               help_text="Darsbay: 1 dars uchun. O'quvchibay: 1 o'quvchi uchun oyiga")
    deduction_percent = models.DecimalField("ushlanma (%)", max_digits=5, decimal_places=2, default=Decimal("0"),
                                            validators=[MinValueValidator(0), MaxValueValidator(100)])
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="xona")
    capacity = models.PositiveSmallIntegerField("sig'imi", default=30)
    students = models.ManyToManyField("people.Student", through="GroupMembership", related_name="groups",
                                      blank=True, verbose_name="o'quvchilar")
    is_active = models.BooleanField("faol", default=True)

    class Meta:
        verbose_name = "guruh"
        verbose_name_plural = "guruhlar"
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "academic_year", "code"], name="unique_group_per_year"),
        ]

    def __str__(self):
        return self.code


class GroupSubject(models.Model):
    """Guruhdagi fan va uning o'qituvchisi. "Birlashma" guruhida bir nechta fan bo'ladi (IT + Fizika)."""

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="subjects", verbose_name="guruh")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, verbose_name="fan")
    teacher = models.ForeignKey("people.Teacher", on_delete=models.PROTECT, related_name="group_subjects",
                                verbose_name="o'qituvchi")
    hours_per_week = models.PositiveSmallIntegerField("haftalik soat", default=0,
                                                      validators=[MaxValueValidator(20)],
                                                      help_text="Dars jadvalidagi limit. 0 — belgilanmagan")

    class Meta:
        verbose_name = "guruh fani"
        verbose_name_plural = "guruh fanlari"
        constraints = [models.UniqueConstraint(fields=["group", "subject"], name="unique_group_subject")]

    def __str__(self):
        return f"{self.group} · {self.subject}"


class GroupMembership(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="memberships")
    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="memberships")
    joined_at = models.DateField("qo'shilgan")
    left_at = models.DateField("chiqqan", null=True, blank=True)

    class Meta:
        verbose_name = "guruh a'zoligi"
        verbose_name_plural = "guruh a'zoliklari"
        constraints = [models.UniqueConstraint(fields=["group", "student"], name="unique_group_member")]

    def __str__(self):
        return f"{self.student} → {self.group}"


class TimeSlot(models.Model):
    """Qo'ng'iroq jadvali: dars raqami va vaqti (filial bo'yicha). Zavuch "Qo'ng'iroqlar" oynasida o'zgartiradi."""

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="time_slots", verbose_name="filial")
    number = models.PositiveSmallIntegerField("dars raqami", validators=[MinValueValidator(1), MaxValueValidator(12)])
    start = models.TimeField("boshlanishi")
    end = models.TimeField("tugashi")
    is_break = models.BooleanField("tanaffus (obed)", default=False, help_text="Bu vaqtga dars qo'yilmaydi")

    class Meta:
        verbose_name = "dars vaqti"
        verbose_name_plural = "dars vaqtlari (qo'ng'iroqlar)"
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "number"], name="unique_slot_number"),
            models.CheckConstraint(condition=models.Q(end__gt=models.F("start")), name="slot_end_after_start"),
        ]

    def __str__(self):
        return f"{self.number}-dars ({self.start:%H:%M}–{self.end:%H:%M})"


class Weekday(models.IntegerChoices):
    MONDAY = 1, "Dushanba"
    TUESDAY = 2, "Seshanba"
    WEDNESDAY = 3, "Chorshanba"
    THURSDAY = 4, "Payshanba"
    FRIDAY = 5, "Juma"
    SATURDAY = 6, "Shanba"


class Lesson(TimeStampedModel):
    """Haftalik jadvaldagi dars: guruh + fan + o'qituvchi, kun va dars raqami, xona.

    Tarix saqlanadi: dars `valid_from`–`valid_to` oralig'ida amal qiladi (`valid_to` bo'sh — hozir ham).
    Jadval o'zgarsa eski yozuv yopiladi, yangisi ochiladi — o'tgan haftalar va darsbay oylik o'zgarmaydi.
    O'qituvchi yozuvning o'zida saqlanadi: guruhda o'qituvchi almashsa, darslar o'sha kundan bo'linadi.
    """

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="lessons", verbose_name="filial")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="lessons",
                                      verbose_name="o'quv yili")
    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="lessons", verbose_name="guruh")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="lessons", verbose_name="fan")
    teacher = models.ForeignKey("people.Teacher", on_delete=models.PROTECT, related_name="lessons",
                                verbose_name="o'qituvchi")
    weekday = models.PositiveSmallIntegerField("hafta kuni", choices=Weekday.choices)
    slot = models.ForeignKey(TimeSlot, on_delete=models.PROTECT, related_name="lessons", verbose_name="dars vaqti")
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="xona")
    valid_from = models.DateField("amal qila boshlagan")
    valid_to = models.DateField("amal qilgan oxirgi kun", null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+",
                                   verbose_name="kiritgan")

    class Meta:
        verbose_name = "dars"
        verbose_name_plural = "darslar (jadval)"
        ordering = ["weekday", "slot__number"]
        indexes = [models.Index(fields=["branch", "weekday", "slot"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=models.F("valid_from")),
                name="lesson_validity_order"),
        ]

    def __str__(self):
        return f"{self.group} · {self.subject} · {self.get_weekday_display()} {self.slot.number}-dars"

    def active_on(self, day) -> bool:
        return self.valid_from <= day and (self.valid_to is None or self.valid_to >= day)


class ClassAttendance(models.Model):
    """Sinf davomati (sinf rahbari kiritadi): bir o'quvchi — bir kun — bitta belgi va izoh (sabab)."""

    class Status(models.TextChoices):
        PRESENT = "B", "Keldi"
        ABSENT = "Y", "Kelmadi"
        LATE = "K", "Kechikdi"
        EXCUSED = "S", "Sababli"

    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, related_name="attendance",
                                     verbose_name="sinf")
    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="class_attendance",
                                verbose_name="o'quvchi")
    date = models.DateField("sana")
    status = models.CharField("belgi", max_length=1, choices=Status.choices)
    note = models.CharField("izoh", max_length=255, blank=True)
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    updated_at = models.DateTimeField("belgilangan", auto_now=True)

    class Meta:
        verbose_name = "sinf davomati"
        verbose_name_plural = "sinf davomati"
        constraints = [models.UniqueConstraint(fields=["student", "date"], name="one_class_mark_per_day")]
        indexes = [models.Index(fields=["school_class", "date"])]

    def __str__(self):
        return f"{self.student} · {self.date} · {self.status}"
