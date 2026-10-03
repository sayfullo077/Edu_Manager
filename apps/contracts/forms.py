from django import forms

from apps.academics.models import SchoolClass
from apps.common.forms import StyledFormMixin
from apps.core.models import AcademicYear
from apps.people.forms import DateInput
from apps.people.models import Guardian

from .models import Contract, ContractTemplate


class TemplateChoiceMixin:
    """Shablon tanlagichi: faqat faol shablonlar, sukut — "sukut bo'yicha" belgilangani."""

    def _setup_template(self):
        field = self.fields["template"]
        field.queryset = ContractTemplate.objects.filter(is_active=True)
        field.empty_label = None
        field.required = False  # bo'sh kelsa — servis sukut shablonni oladi
        field.label = "Shablon"
        if not self.initial.get("template") and not getattr(self.instance, "template_id", None):
            self.initial["template"] = field.queryset.order_by("-is_default", "name").first()


class ContractForm(TemplateChoiceMixin, StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Contract
        fields = ["template", "full_tariff", "discount_percent", "discount_reason", "start_date", "end_date",
                  "notes"]
        widgets = {
            "full_tariff": forms.NumberInput(attrs={"step": "1000", "min": "0", "data-money": ""}),
            "discount_percent": forms.NumberInput(attrs={"step": "0.5", "min": "0", "max": "100"}),
            "start_date": DateInput(),
            "end_date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_template()


class AdmissionContractForm(TemplateChoiceMixin, StyledFormMixin, forms.ModelForm):
    """Qabul formasidagi "Moliya (tarif)" bo'limi — shartnoma qoralamasi shu ma'lumot bilan tuziladi."""

    class Meta:
        model = Contract
        fields = ["full_tariff", "start_date", "discount_percent", "discount_reason", "template"]
        widgets = {
            "full_tariff": forms.NumberInput(attrs={"step": "1000", "min": "0", "data-tariff-input": ""}),
            "discount_percent": forms.NumberInput(attrs={"step": "0.5", "min": "0", "max": "100"}),
            "start_date": DateInput(),
        }
        labels = {"full_tariff": "Tarif (oyiga, chegirmasiz)", "discount_percent": "Chegirma %",
                  "start_date": "Boshlanish sanasi"}
        help_texts = {"full_tariff": "Sinf tanlanganda sinf tarifi avtomatik qo'yiladi.",
                      "start_date": "Birinchi oy to'lovi shu sanadan hisoblanadi."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_template()


class ContractTemplateForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ContractTemplate
        fields = ["name", "body", "is_active", "is_default"]
        widgets = {"body": forms.Textarea(attrs={"rows": 28, "spellcheck": "false", "class": "template-editor"})}
        labels = {"is_default": "Sukut bo'yicha (yangi shartnomalarda tanlangan turadi)"}


class NewContractForm(TemplateChoiceMixin, StyledFormMixin, forms.ModelForm):
    """"Yangi shartnoma" sahifasi (asl tizimdagidek): o'quvchi → uning vasiysi, shablon, o'quv yili, tarif.

    `student` berilsa (o'quvchi kartasidan kelinganda) — o'quvchi tanlagichi yo'q, faqat shu o'quvchi.
    """

    student = forms.ModelChoiceField(label="O'quvchi", queryset=None, empty_label="— O'quvchini tanlang —")
    guardian = forms.ModelChoiceField(label="Vasiy (shartnoma kimga)", queryset=None, required=False,
                                      empty_label="— Asosiy vasiy —")
    academic_year = forms.ModelChoiceField(label="O'quv yili", queryset=AcademicYear.objects.order_by("-start_date"),
                                           empty_label=None, required=False)  # bo'sh — joriy o'quv yili

    class Meta:
        model = Contract
        fields = ["template", "full_tariff", "discount_percent", "discount_reason", "start_date", "notes"]
        widgets = {
            "full_tariff": forms.NumberInput(attrs={"step": "1000", "min": "0", "data-tariff-input": ""}),
            "discount_percent": forms.NumberInput(attrs={"step": "0.5", "min": "0", "max": "100"}),
            "start_date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {"full_tariff": "Tarif (oyiga, chegirmasiz)", "discount_percent": "Chegirma %"}
        help_texts = {"full_tariff": "O'quvchi tanlanganda sinf tarifi avtomatik qo'yiladi.",
                      "start_date": "Bo'sh qolsa — qabul sanasi yoki o'quv yili boshi."}

    def __init__(self, *args, candidates, fixed_student=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_template()
        self.fixed_student = fixed_student
        if fixed_student:
            del self.fields["student"]
            guardians = Guardian.objects.filter(child_links__student=fixed_student)
        else:
            self.fields["student"].queryset = candidates
            self.fields["student"].label_from_instance = lambda s: (
                f"{s.full_name} · {s.code}" + (f" · {s.school_class.name}" if s.school_class else ""))
            self.fields["student"].widget.attrs.update({"data-contract-student": "", "size": 7})
            guardians = Guardian.objects.filter(child_links__student__in=candidates)
        self.fields["guardian"].queryset = guardians.distinct()
        self.fields["guardian"].widget.attrs["data-contract-guardian"] = ""
        self.fields["start_date"].required = False

    def clean(self):
        d = super().clean()
        student = self.fixed_student or d.get("student")
        if student and d.get("guardian") and not student.guardian_links.filter(guardian=d["guardian"]).exists():
            self.add_error("guardian", "Bu vasiy tanlangan o'quvchiga biriktirilmagan.")
        return d


class CodeForm(StyledFormMixin, forms.Form):
    code = forms.CharField(label="Ota-onaga kelgan kod", min_length=6, max_length=6,
                           widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off",
                                                         "placeholder": "••••••"}))


class CancelForm(StyledFormMixin, forms.Form):
    reason = forms.CharField(label="Bekor qilish sababi", max_length=255)


class ScanForm(forms.Form):
    scan = forms.FileField(label="Imzolangan shartnoma skaneri (PDF, 5 MB gacha)",
                           widget=forms.ClearableFileInput(attrs={"accept": "application/pdf"}))


class ContractFilterForm(forms.Form):
    """Shartnomalar ro'yxati filtri (asl tizimdagidek: yil, sinf, holat — "Muddati o'tgan" ham)."""

    EXPIRED = "expired"
    FILTERS = [("academic_year", "Barcha yillar", "calendar"), ("school_class", "Barcha sinflar", "school"),
               ("status", "Barcha holatlar", "shield")]

    q = forms.CharField(required=False, max_length=100)
    academic_year = forms.ModelChoiceField(required=False, queryset=AcademicYear.objects.order_by("-start_date"),
                                           empty_label="Barcha yillar")
    school_class = forms.ModelChoiceField(required=False, queryset=None, empty_label="Barcha sinflar")
    status = forms.ChoiceField(required=False, choices=[("", "Barcha holatlar"), *Contract.Status.choices,
                                                        (EXPIRED, "Muddati o'tgan")])

    def __init__(self, *args, branch, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["school_class"].queryset = (SchoolClass.objects.filter(branch=branch, is_active=True)
                                                .order_by("kind", "grade", "name"))
        for name, label, _ in self.FILTERS:
            self.fields[name].widget.attrs.update({"class": "input", "aria-label": label})

    def active_filters(self) -> set[str]:
        return {name for name, _, _ in self.FILTERS if self.data.get(name)}

    def values(self) -> dict:
        d = self.cleaned_data if self.is_valid() else {}
        return {"q": (d.get("q") or "").strip(), "status": d.get("status", ""),
                "academic_year": d["academic_year"].pk if d.get("academic_year") else None,
                "school_class": d["school_class"].pk if d.get("school_class") else None}
