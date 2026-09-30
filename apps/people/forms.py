from decimal import Decimal

from django import forms
from django.core.validators import MaxLengthValidator

from apps.accounts.forms import PhoneField
from apps.common.forms import StyledFormMixin
from apps.common.templatetags.ui import money
from apps.core.models import AcademicYear

from . import selectors
from .domain.regions import region_choices
from .models import Gender, Guardian, Student, StudentGuardian


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%d", **kwargs)


class SchoolClassSelect(forms.Select):
    """Har bir sinf variantida o'quv yili (data-year) — "O'quv yili" tanlanganda JS sinflarni saralaydi;
    grade va tarif (data-grade, data-tariff) — sinf tanlanganda qabul formasida avtomatik to'ldiriladi."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, "instance", None)
        if instance is not None:
            option["attrs"]["data-year"] = instance.academic_year_id
            option["attrs"]["data-tariff"] = int(instance.monthly_tariff)
            if instance.grade:
                option["attrs"]["data-grade"] = instance.grade
        return option


class StudentForm(StyledFormMixin, forms.ModelForm):
    DOC_TYPES = [("birth_certificate", "Tug'ilganlik guvohnomasi (metrika)"), ("passport", "Passport")]

    phone = PhoneField(label="Telefon", required=False)
    region = forms.ChoiceField(label="Viloyat", required=False)
    doc_type = forms.ChoiceField(label="Hujjat turi", choices=DOC_TYPES, required=False, widget=forms.RadioSelect)
    academic_year = forms.ModelChoiceField(label="O'quv yili", required=False, empty_label="Barcha yillar",
                                           queryset=AcademicYear.objects.order_by("-start_date"))

    class Meta:
        model = Student
        fields = ["last_name", "first_name", "middle_name", "birth_date", "gender", "phone",
                  "birth_certificate", "passport", "pinfl", "region", "district", "mahalla", "address",
                  "grade", "school_class", "status", "joined_at", "left_at", "in_erp", "in_emaktab", "notes"]
        widgets = {
            "birth_date": DateInput(),
            "joined_at": DateInput(),
            "left_at": DateInput(),
            "gender": forms.RadioSelect,
            "school_class": SchoolClassSelect,
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {"left_at": "Bitirgan / ketgan sanasi", "grade": "Grade (davlat standarti)",
                  "address": "Ko'cha, uy (qo'shimcha)", "school_class": "Sinf"}

    def __init__(self, *args, branch, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["school_class"].queryset = selectors.class_choices(branch, all_years=True)
        self.fields["school_class"].empty_label = "— Tanlanmagan —"
        self.fields["school_class"].widget.attrs["data-class-select"] = ""
        self.fields["academic_year"].widget.attrs["data-year-select"] = ""
        instance = self.instance
        current_class = instance.school_class if instance.pk else None
        year = current_class.academic_year if current_class else AcademicYear.current()
        self.initial.setdefault("academic_year", year.pk if year else None)
        self.fields["region"].choices = region_choices(instance.region if instance.pk else "")
        self.initial.setdefault("doc_type", "passport" if instance.pk and instance.passport else "birth_certificate")
        self._setup_address(instance)
        self.fields["gender"].choices = Gender.choices  # radio'da bo'sh "-----" varianti chiqmasin
        for name in ("last_name", "first_name"):
            self.fields[name].widget.attrs["autocomplete"] = "off"
        # "AD 1234567" kabi bo'shliq bilan kiritilishi mumkin — uzunlik tozalangach model validatorida tekshiriladi.
        for name, limit in (("birth_certificate", 24), ("passport", 12)):
            field = self.fields[name]
            field.max_length = limit
            field.validators = [v for v in field.validators if not isinstance(v, MaxLengthValidator)]
            field.widget.attrs.update({"data-upper": "", "autocomplete": "off", "maxlength": limit})
        self.fields["pinfl"].widget.attrs.update({"inputmode": "numeric", "autocomplete": "off"})
        self.fields["passport"].help_text = "16 yoshdan katta bo'lsa"

    def _setup_address(self, instance):
        """Viloyat → tuman — bog'liq tanlagich (JS viloyat o'zgarganda tumanlarni almashtiradi);
        mahalla — ma'lumotnomadan taklif qilinadigan matn (yangisi saqlanganda bazaga tushadi)."""
        region = self.data.get(self.add_prefix("region")) if self.is_bound else (instance.region or "")
        current = self.data.get(self.add_prefix("district")) if self.is_bound else (instance.district or "")
        names = selectors.district_map().get(region or "", [])
        choices = [("", "— Avval viloyatni tanlang —" if not region else "— Tanlang —"), *((n, n) for n in names)]
        if current and current not in names:
            choices.append((current, current))  # ro'yxatda yo'q eski qiymat yo'qolmasin
        self.fields["district"].widget = forms.Select(choices=choices, attrs={"data-district": ""})
        self.fields["region"].widget.attrs["data-region"] = ""
        self.fields["mahalla"].widget.attrs.update({"list": "mahalla-options", "data-mahalla": "",
                                                    "placeholder": "Tanlang yoki yangi nom yozing",
                                                    "autocomplete": "off"})
        self.fields["mahalla"].label = "Mahalla / qishloq (MFY)"
        for name in ("region", "district", "mahalla", "address"):
            self.fields[name].widget.attrs["class"] = self.fields[name].widget.attrs.get("class", "input")
        self.fields["address"].widget.attrs.setdefault("placeholder", "Ko'cha nomi, uy/xonadon raqami")

    def clean_passport(self):
        return (self.cleaned_data.get("passport") or "").replace(" ", "").upper()

    def clean_birth_certificate(self):
        return (self.cleaned_data.get("birth_certificate") or "").replace(" ", "").upper()

    def clean_pinfl(self):
        return "".join((self.cleaned_data.get("pinfl") or "").split())


YES_NO = [("", "Barchasi"), ("1", "Kiritilgan"), ("0", "Kiritilmagan")]


def _yes_no(value: str) -> bool | None:
    return {"1": True, "0": False}.get(value)


class StudentFilterForm(forms.Form):
    """O'quvchilar ro'yxati filtri. `FILTERS` — "Filtr qo'shish" menyusidagi tartib va nomlar."""

    FILTERS = [
        ("academic_year", "O'quv yili", "calendar"),
        ("school_class", "Sinf", "school"),
        ("grade", "Grade (davlat standarti)", "graduation"),
        ("tariff", "Tarif", "wallet"),
        ("gender", "Jins", "users"),
        ("status", "Status", "check"),
        ("joined", "Qabul sanasi", "clock"),
        ("in_erp", "ERP", "switch"),
        ("in_emaktab", "E-MAKTAB", "switch"),
    ]

    q = forms.CharField(required=False, max_length=100, label="Qidirish")
    status = forms.ChoiceField(required=False, choices=[("", "Barcha holatlar"), *Student.Status.choices])
    school_class = forms.ModelChoiceField(required=False, queryset=None, empty_label="Barcha sinflar")
    gender = forms.ChoiceField(required=False, choices=[("", "Barchasi"), *Gender.choices])
    academic_year = forms.ModelChoiceField(required=False, queryset=AcademicYear.objects.order_by("-start_date"),
                                           empty_label="Barcha yillar")
    grade = forms.TypedChoiceField(required=False, coerce=int, empty_value=None,
                                   choices=[("", "Barchasi"), *((g, f"{g}-sinf") for g in range(1, 12))])
    tariff = forms.TypedChoiceField(required=False, coerce=Decimal, empty_value=None)
    joined_from = forms.DateField(required=False, widget=DateInput(attrs={"aria-label": "Qabul sanasi (dan)"}))
    joined_to = forms.DateField(required=False, widget=DateInput(attrs={"aria-label": "Qabul sanasi (gacha)"}))
    in_erp = forms.ChoiceField(required=False, choices=YES_NO)
    in_emaktab = forms.ChoiceField(required=False, choices=YES_NO)

    def __init__(self, *args, branch, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["school_class"].queryset = selectors.class_choices(branch)
        self.fields["tariff"].choices = [("", "Barchasi"), *((str(t), money(t)) for t in
                                                             selectors.tariff_choices(branch))]
        labels = {name: label for name, label, _ in self.FILTERS}
        for name, field in self.fields.items():
            if name == "q":
                continue
            field.widget.attrs.setdefault("aria-label", labels.get(name, ""))
            # Avtomatik yuborilmaydi: bir nechta filtr tanlab, bitta so'rov bilan "Qidirish" bosiladi.
            field.widget.attrs["class"] = "input"
        # "Barcha holatlar" ham yuborilsin — aks holda sukut (Faol) qaytib qo'yiladi.
        self.fields["status"].widget.attrs["data-keep-empty"] = ""

    def active_filters(self) -> set[str]:
        """Qiymati bor filtrlar — sahifada ochiq ko'rsatiladi va menyuda ✓ bilan belgilanadi."""
        data = self.data
        active = {name for name, _, _ in self.FILTERS if data.get(name)}
        if data.get("joined_from") or data.get("joined_to"):
            active.add("joined")
        return active

    def to_filters(self) -> selectors.StudentFilters:
        if not self.is_valid():
            return selectors.StudentFilters(status=Student.Status.ACTIVE)
        d = self.cleaned_data
        return selectors.StudentFilters(
            q=d["q"].strip(), status=d["status"], gender=d["gender"],
            school_class=d["school_class"].pk if d["school_class"] else None,
            academic_year=d["academic_year"].pk if d["academic_year"] else None,
            grade=d["grade"], tariff=d["tariff"], joined_from=d["joined_from"], joined_to=d["joined_to"],
            in_erp=_yes_no(d["in_erp"]), in_emaktab=_yes_no(d["in_emaktab"]),
        )


class GuardianForm(StyledFormMixin, forms.ModelForm):
    phone = PhoneField(label="Telefon")
    extra_phone = PhoneField(label="Qo'shimcha telefon", required=False)

    class Meta:
        model = Guardian
        fields = ["last_name", "first_name", "middle_name", "phone", "extra_phone", "passport", "pinfl",
                  "address", "workplace", "position"]
        widgets = {
            "passport": forms.TextInput(attrs={"placeholder": "AB1234567", "autocomplete": "off",
                                               "data-upper": ""}),
            "pinfl": forms.TextInput(attrs={"placeholder": "14 ta raqam", "inputmode": "numeric",
                                            "autocomplete": "off", "maxlength": 14}),
        }
        help_texts = {"pinfl": "Kiritilsa, ota-ona tizimda bor-yo'qligi aniq tekshiriladi."}

    def clean_passport(self):
        return (self.cleaned_data.get("passport") or "").replace(" ", "").upper()

    def clean_pinfl(self):
        return "".join((self.cleaned_data.get("pinfl") or "").split())


class AdmissionGuardianForm(GuardianForm):
    """Qabul formasidagi vasiy (Ota / Ona / Olib keluvchi) — asl tizimdagidek hujjatlar bilan majburiy."""

    extra_phone = None

    class Meta(GuardianForm.Meta):
        fields = ["pinfl", "last_name", "first_name", "middle_name", "phone", "passport"]
        labels = {"pinfl": "JSHSHIR (14 xonali)", "passport": "Passport (seriya va raqam)"}
        help_texts = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("pinfl", "middle_name", "passport"):
            self.fields[name].required = True


class AdmissionForm(forms.Form):
    """Qabul formasining umumiy qismi: olib keluvchining kimligi va shartnoma kim nomiga tuziladi."""

    SLOTS = [("father", "Ota"), ("mother", "Ona"), ("carrier", "Olib keluvchi")]
    CARRIER_RELATIONS = [c for c in StudentGuardian.Relation.choices
                         if c[0] not in (StudentGuardian.Relation.FATHER, StudentGuardian.Relation.MOTHER)]

    carrier_relation = forms.ChoiceField(label="Kim bo'ladi?", choices=CARRIER_RELATIONS, required=False,
                                         initial=StudentGuardian.Relation.OTHER)
    signer = forms.ChoiceField(label="Shartnoma vasiysi", choices=SLOTS, widget=forms.RadioSelect,
                               error_messages={"required": "Shartnoma kim nomiga tuzilishini tanlang."})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["carrier_relation"].widget.attrs["class"] = "input"


class RelationForm(forms.Form):
    relation = forms.ChoiceField(label="Kim bo'ladi?", choices=StudentGuardian.Relation.choices,
                                 widget=forms.RadioSelect, initial=StudentGuardian.Relation.FATHER)
    is_primary = forms.BooleanField(label="Asosiy aloqa (shartnoma va SMS shu odamga)", required=False)


class GuardianFilterForm(forms.Form):
    """Ota-onalar ro'yxati filtri ("Filtr qo'shish" menyusi — o'quvchilar ro'yxatidagi bilan bir xil)."""

    FILTERS = [("relation", "Munosabat", "users"), ("status", "Holat", "check")]

    q = forms.CharField(required=False, max_length=100)
    relation = forms.ChoiceField(required=False, choices=[("", "Munosabat"), *StudentGuardian.Relation.choices])
    status = forms.ChoiceField(required=False, choices=[("", "Barchasi"), *Guardian.Status.choices])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {name: label for name, label, _ in self.FILTERS}
        for name in ("relation", "status"):
            self.fields[name].widget.attrs.update({"class": "input", "aria-label": labels[name]})

    def active_filters(self) -> set[str]:
        return {name for name, _, _ in self.FILTERS if self.data.get(name)}

    def values(self) -> dict:
        d = self.cleaned_data if self.is_valid() else {}
        return {"q": (d.get("q") or "").strip(), "relation": d.get("relation", ""), "status": d.get("status", "")}
