from django import forms

from apps.academics.models import SchoolClass
from apps.common.forms import StyledFormMixin
from apps.core.models import AcademicYear
from apps.people.forms import DateInput

from .models import Contract


class ContractForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Contract
        fields = ["full_tariff", "discount_percent", "discount_reason", "start_date", "end_date", "notes"]
        widgets = {
            "full_tariff": forms.NumberInput(attrs={"step": "1000", "min": "0", "data-money": ""}),
            "discount_percent": forms.NumberInput(attrs={"step": "0.5", "min": "0", "max": "100"}),
            "start_date": DateInput(),
            "end_date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class AdmissionContractForm(StyledFormMixin, forms.ModelForm):
    """Qabul formasidagi "Moliya (tarif)" bo'limi — shartnoma qoralamasi shu ma'lumot bilan tuziladi."""

    class Meta:
        model = Contract
        fields = ["full_tariff", "start_date", "discount_percent", "discount_reason"]
        widgets = {
            "full_tariff": forms.NumberInput(attrs={"step": "1000", "min": "0", "data-tariff-input": ""}),
            "discount_percent": forms.NumberInput(attrs={"step": "0.5", "min": "0", "max": "100"}),
            "start_date": DateInput(),
        }
        labels = {"full_tariff": "Tarif (oyiga, chegirmasiz)", "discount_percent": "Chegirma %",
                  "start_date": "Boshlanish sanasi"}
        help_texts = {"full_tariff": "Sinf tanlanganda sinf tarifi avtomatik qo'yiladi.",
                      "start_date": "Birinchi oy to'lovi shu sanadan hisoblanadi."}


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
