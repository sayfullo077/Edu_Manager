from datetime import date

from django import forms

from .models import PayrollSettings, SalaryPayment
from .services.settings import FIELDS


def parse_month(value: str | None, default: date) -> date:
    """«2026-09» → 2026-09-01; noto'g'ri qiymatda — sukut."""
    try:
        y, m = (int(x) for x in (value or "").split("-"))
        return date(y, m, 1)
    except (ValueError, TypeError):
        return default.replace(day=1)


class PenaltyForm(forms.Form):
    amount = forms.DecimalField(label="Summa (so'm)", min_value=1, max_digits=14, decimal_places=2,
                                widget=forms.NumberInput(attrs={"class": "input", "inputmode": "numeric",
                                                                "placeholder": "100 000"}))
    reason = forms.CharField(label="Sababi", max_length=255, widget=forms.TextInput(
        attrs={"class": "input", "placeholder": "Masalan: darsga kechikish"}))


class CancelPenaltyForm(forms.Form):
    reason = forms.CharField(label="Bekor qilish sababi", max_length=255,
                             widget=forms.TextInput(attrs={"class": "input"}))


class PayrollSettingsForm(forms.ModelForm):
    class Meta:
        model = PayrollSettings
        fields = FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, f in self.fields.items():
            f.widget.attrs.update({"class": "input", "inputmode": "decimal"})
            if name.endswith("percent"):
                f.widget.attrs.update({"step": "0.01", "min": 0, "max": 100})


class SalaryPaymentForm(forms.Form):
    ACCOUNTS = [("cash", "Naqd kassa"), ("bank", "Bank hisobi")]

    kind = forms.ChoiceField(label="Turi", choices=SalaryPayment.Kind.choices,
                             widget=forms.RadioSelect, initial=SalaryPayment.Kind.ADVANCE)
    amount = forms.DecimalField(label="Summa (so'm)", min_value=1, max_digits=14, decimal_places=2,
                                widget=forms.NumberInput(attrs={"class": "input", "inputmode": "numeric"}))
    account_kind = forms.ChoiceField(label="Qayerdan", choices=ACCOUNTS, initial="cash",
                                     widget=forms.Select(attrs={"class": "input"}))
    paid_on = forms.DateField(label="Sana", widget=forms.DateInput(attrs={"class": "input", "type": "date"},
                                                                    format="%Y-%m-%d"))
    note = forms.CharField(label="Izoh", max_length=255, required=False,
                           widget=forms.TextInput(attrs={"class": "input"}))
