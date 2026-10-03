from datetime import date

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models.functions import Upper

from apps.academics.models import Language, SchoolClass, Subject
from apps.common import crypto
from apps.common.fields import EncryptedCharField
from apps.common.models import CodeSequence
from apps.core.models import Branch, TimeStampedModel

pinfl_validator = RegexValidator(r"^\d{14}$", "JSHSHIR 14 ta raqamdan iborat.")
passport_validator = RegexValidator(r"^[A-Z]{2}\d{7}$", "Passport: 2 ta lotin harf va 7 ta raqam (AB1234567).")


class Gender(models.TextChoices):
    MALE = "M", "O'g'il"
    FEMALE = "F", "Qiz"


class District(models.Model):
    """Tuman / shahar (viloyat — `domain.regions.REGIONS` dagi nom). Boshlang'ich ro'yxat migration'da."""

    region = models.CharField("viloyat", max_length=80, db_index=True)
    name = models.CharField("tuman / shahar", max_length=80)
    is_active = models.BooleanField("faol", default=True)

    class Meta:
        verbose_name = "tuman / shahar"
        verbose_name_plural = "tumanlar / shaharlar"
        ordering = ["region", "name"]
        constraints = [models.UniqueConstraint(fields=["region", "name"], name="unique_district_per_region")]

    def __str__(self):
        return f"{self.name} ({self.region})"


class Mahalla(models.Model):
    """Mahalla / qishloq (MFY, SHFY, QFY). Admin qo'shadi yoki forma orqali birinchi kiritilganda yaratiladi."""

    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name="mahallas",
                                 verbose_name="tuman / shahar")
    name = models.CharField("mahalla / qishloq", max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "mahalla"
        verbose_name_plural = "mahallalar"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(Upper("name"), "district", name="unique_mahalla_per_district")]

    def __str__(self):
        return self.name


class PersonNameMixin(models.Model):
    last_name = models.CharField("familiya", max_length=60)
    first_name = models.CharField("ism", max_length=60)
    middle_name = models.CharField("otasining ismi", max_length=80, blank=True)

    class Meta:
        abstract = True

    @property
    def full_name(self):
        return " ".join(p for p in [self.last_name, self.first_name, self.middle_name] if p)

    @property
    def short_name(self):
        return f"{self.last_name} {self.first_name}"

    @property
    def initials(self):
        return f"{self.last_name[:1]}{self.first_name[:1]}".upper()


class IdentityDocsMixin(models.Model):
    """Passport va JSHSHIR: bazada shifrlangan, qidirish faqat blind index orqali (aniq moslik)."""

    passport = EncryptedCharField("passport", max_length=9, blank=True, validators=[passport_validator])
    pinfl = EncryptedCharField("JSHSHIR", max_length=14, blank=True, validators=[pinfl_validator])
    pinfl_index = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    passport_index = models.CharField(max_length=64, blank=True, db_index=True, editable=False)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.passport = (self.passport or "").replace(" ", "").upper()
        self.pinfl_index = crypto.blind_index(self.pinfl) if self.pinfl else ""
        self.passport_index = crypto.blind_index(self.passport) if self.passport else ""
        super().save(*args, **kwargs)


birth_certificate_validator = RegexValidator(r"^[A-Z0-9-]{5,20}$",
                                              "Guvohnoma raqami: lotin harflari, raqam va chiziqcha (I-FR-1234567).")


class Student(PersonNameMixin, IdentityDocsMixin, TimeStampedModel):
    class Status(models.TextChoices):
        # Tartib asl tizimdagi filtrdagidek
        ACTIVE = "active", "Faol"
        INACTIVE = "inactive", "Nofaol"
        GRADUATED = "graduated", "Bitirgan"
        EXPELLED = "expelled", "O'qishdan chiqarilgan"
        FROZEN = "frozen", "Ta'tilda"
        LEFT = "left", "Ketgan"

    # Maktabni tark etgan holatlar — ketgan sana (left_at) majburiy, yangi oy grafigi yaratilmaydi
    GONE_STATUSES = (Status.LEFT, Status.GRADUATED, Status.EXPELLED)

    code = models.CharField("kodi", max_length=20, unique=True, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="students", verbose_name="filial")
    birth_date = models.DateField("tug'ilgan sana")
    gender = models.CharField("jinsi", max_length=1, choices=Gender.choices)
    phone = models.CharField("telefon", max_length=12, blank=True)
    birth_certificate = EncryptedCharField("tug'ilganlik guvohnomasi", max_length=20, blank=True,
                                           validators=[birth_certificate_validator])
    region = models.CharField("viloyat", max_length=80, blank=True)
    district = models.CharField("tuman / shahar", max_length=80, blank=True)
    mahalla = models.CharField("mahalla / qishloq", max_length=120, blank=True)
    address = models.CharField("ko'cha / uy", max_length=255, blank=True)
    grade = models.PositiveSmallIntegerField("sinf (daraja)", validators=[MinValueValidator(1), MaxValueValidator(11)])
    school_class = models.ForeignKey(SchoolClass, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="students", verbose_name="sinf / yo'nalish")
    status = models.CharField("holati", max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    in_erp = models.BooleanField("ERP'ga kiritilgan", default=False)
    in_emaktab = models.BooleanField("E-maktab'ga kiritilgan", default=False)
    joined_at = models.DateField("qabul qilingan")
    left_at = models.DateField("ketgan sana", null=True, blank=True)
    notes = models.TextField("izoh", blank=True)

    class Meta:
        verbose_name = "o'quvchi"
        verbose_name_plural = "o'quvchilar"
        ordering = ["last_name", "first_name"]
        indexes = [
            models.Index(fields=["branch", "status"]),
            models.Index(Upper("last_name"), name="student_last_name_upper"),
        ]

    def __str__(self):
        return self.full_name

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = CodeSequence.next_code("STD", (self.joined_at or date.today()).year)
        self.birth_certificate = (self.birth_certificate or "").replace(" ", "").upper()
        super().save(*args, **kwargs)

    @property
    def has_address(self) -> bool:
        return any([self.region, self.district, self.mahalla, self.address])


class Guardian(PersonNameMixin, IdentityDocsMixin, TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Faol"
        INACTIVE = "inactive", "Nofaol"

    phone = models.CharField("telefon", max_length=12)
    extra_phone = models.CharField("qo'shimcha telefon", max_length=12, blank=True)
    address = models.CharField("manzil", max_length=255, blank=True)
    workplace = models.CharField("ish joyi", max_length=160, blank=True)
    position = models.CharField("lavozimi", max_length=120, blank=True)
    status = models.CharField("holati", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    children = models.ManyToManyField(Student, through="StudentGuardian", related_name="guardians",
                                      verbose_name="farzandlari")

    class Meta:
        verbose_name = "ota-ona / vasiy"
        verbose_name_plural = "ota-onalar"
        ordering = ["last_name", "first_name"]
        indexes = [models.Index(fields=["phone"])]

    def __str__(self):
        return self.full_name


class StudentGuardian(models.Model):
    class Relation(models.TextChoices):
        FATHER = "father", "Ota"
        MOTHER = "mother", "Ona"
        GRANDFATHER = "grandpa", "Buva"
        GRANDMOTHER = "grandma", "Buvi"
        UNCLE = "uncle", "Tog'a"
        AUNT = "aunt", "Xola"
        OTHER = "other", "Boshqa"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="guardian_links")
    guardian = models.ForeignKey(Guardian, on_delete=models.CASCADE, related_name="child_links")
    relation = models.CharField("munosabati", max_length=10, choices=Relation.choices)
    is_primary = models.BooleanField("asosiy aloqa", default=False,
                                     help_text="Shartnoma va SMS'lar shu odamga yuboriladi")

    class Meta:
        verbose_name = "o'quvchi — ota-ona"
        verbose_name_plural = "o'quvchi — ota-ona"
        constraints = [
            models.UniqueConstraint(fields=["student", "guardian"], name="unique_student_guardian"),
            models.UniqueConstraint(fields=["student"], condition=models.Q(is_primary=True),
                                    name="one_primary_guardian_per_student"),
        ]

    def __str__(self):
        return f"{self.guardian} ({self.get_relation_display()}) → {self.student}"


class Teacher(IdentityDocsMixin, TimeStampedModel):
    """O'qituvchi profili. Ism/telefon/login `User` modelida — takrorlanmaydi."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Faol"
        INACTIVE = "inactive", "Nofaol"
        VACATION = "vacation", "Ta'tilda"
        DISMISSED = "dismissed", "Bo'shatilgan"

    class Kind(models.TextChoices):
        TEACHER = "teacher", "O'qituvchi"
        COORDINATOR = "coordinator", "Koordinator"
        ASSISTANT = "assistant", "Yordamchi o'qituvchi"

    class Category(models.TextChoices):
        FIRST = "first", "1-toifa"
        SECOND = "second", "2-toifa"
        SPECIALIST = "specialist", "Mutaxassis"
        HIGHEST = "highest", "Oliy toifa"

    # Jadvalga qo'yib, guruhga biriktirib bo'lmaydigan holatlar
    NOT_WORKING = (Status.INACTIVE, Status.DISMISSED)

    class Education(models.TextChoices):
        SECONDARY = "secondary", "O'rta"
        VOCATIONAL = "vocational", "O'rta maxsus"
        HIGHER = "higher", "Oliy"
        MASTER = "master", "Magistr"

    class MaritalStatus(models.TextChoices):
        SINGLE = "single", "Turmush qurmagan"
        MARRIED = "married", "Turmush qurgan"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="teacher",
                                verbose_name="foydalanuvchi")
    code = models.CharField("kodi", max_length=20, unique=True, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="teachers", verbose_name="filial")
    birth_date = models.DateField("tug'ilgan sana", null=True, blank=True)
    gender = models.CharField("jinsi", max_length=1, choices=Gender.choices, blank=True)
    address = models.CharField("manzil", max_length=255, blank=True)
    marital_status = models.CharField("oilaviy holati", max_length=10, choices=MaritalStatus.choices, blank=True)
    education = models.CharField("ma'lumoti", max_length=12, choices=Education.choices, blank=True)
    specialty = models.CharField("mutaxassisligi", max_length=160, blank=True)
    experience_years = models.PositiveSmallIntegerField("ish staji (yil)", default=0)
    kind = models.CharField("turi", max_length=12, choices=Kind.choices, default=Kind.TEACHER, db_index=True)
    category = models.CharField("toifasi", max_length=12, choices=Category.choices, blank=True)
    hired_at = models.DateField("ishga qabul", null=True, blank=True)
    contract_start = models.DateField("shartnoma boshlanishi", null=True, blank=True)
    contract_end = models.DateField("shartnoma tugashi", null=True, blank=True)
    status = models.CharField("holati", max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    subjects = models.ManyToManyField(Subject, related_name="teachers", blank=True, verbose_name="o'qitish fanlari")
    email = models.EmailField("email", blank=True)
    card_number = EncryptedCharField("karta raqami (oylik uchun)", max_length=16, blank=True,
                                     validators=[RegexValidator(r"^\d{16}$", "Karta raqami 16 ta raqam.")])
    official_employment = models.BooleanField("ish staji yoziladi (mehnat daftarchasi)", default=False)
    fixed_salary = models.DecimalField("belgilangan oylik (so'm)", max_digits=12, decimal_places=2, default=0,
                                       help_text="Darsbay/o'quvchibay hisobdan tashqari qat'iy oylik. 0 — yo'q")
    notes = models.TextField("izoh", blank=True)
    teaching_languages = ArrayField(models.CharField(max_length=2, choices=Language.choices), default=list,
                                    blank=True, verbose_name="o'qitish tillari")

    class Meta:
        verbose_name = "o'qituvchi"
        verbose_name_plural = "o'qituvchilar"
        ordering = ["user__last_name", "user__first_name"]

    def __str__(self):
        return self.user.full_name

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = CodeSequence.next_code("TCH", (self.hired_at or date.today()).year)
        super().save(*args, **kwargs)


class Certificate(TimeStampedModel):
    """O'qituvchi sertifikati (milliy, IELTS, CEFR ...) — ustama hisobi va HR uchun."""

    class Kind(models.TextChoices):
        NATIONAL = "national", "Milliy sertifikat"
        IELTS = "ielts", "IELTS"
        CEFR = "cefr", "CEFR"
        TOEFL = "toefl", "TOEFL"
        OTHER = "other", "Boshqa"

    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="certificates",
                                verbose_name="o'qituvchi")
    kind = models.CharField("sertifikat turi", max_length=10, choices=Kind.choices)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, null=True, blank=True, verbose_name="fan")
    number = models.CharField("sertifikat raqami / darajasi", max_length=40, blank=True)
    issued_on = models.DateField("boshlanish sanasi")
    expires_on = models.DateField("tugash sanasi")
    score = models.DecimalField("ball", max_digits=6, decimal_places=2, null=True, blank=True)
    issued_by = models.CharField("kim tomonidan berilgan", max_length=160, blank=True)

    class Meta:
        verbose_name = "sertifikat"
        verbose_name_plural = "sertifikatlar"
        ordering = ["-expires_on"]
        constraints = [models.CheckConstraint(condition=models.Q(expires_on__gte=models.F("issued_on")),
                                              name="certificate_dates_order")]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.teacher}"

    @property
    def is_valid(self) -> bool:
        return self.expires_on >= date.today()
