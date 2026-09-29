from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError

from apps.core.models import Branch

from .domain.phone import normalize_phone
from .models import OneTimeCode


class BranchMixin(forms.Form):
    """Filial maydoni faqat bir nechta faol filial bo'lsa ko'rsatiladi."""

    branch = forms.ModelChoiceField(queryset=Branch.objects.none(), label="Filial", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        branches = Branch.objects.filter(is_active=True)
        self.fields["branch"].queryset = branches
        self.show_branch = branches.count() > 1
        if self.show_branch:
            self.fields["branch"].required = True
            self.fields["branch"].empty_label = "Filialni tanlang"
        else:
            self.fields["branch"].widget = forms.HiddenInput()
            self.fields["branch"].initial = branches.first()

    def clean_branch(self):
        return self.cleaned_data.get("branch") or self.fields["branch"].queryset.first()


class PhoneField(forms.CharField):
    def __init__(self, **kwargs):
        kwargs.setdefault("label", "Telefon raqam")
        kwargs.setdefault("max_length", 20)
        super().__init__(**kwargs)
        self.widget.attrs.update({
            "inputmode": "tel",
            "autocomplete": "tel-national",
            "placeholder": "90 123 45 67",
            "data-phone-mask": "",
        })

    def prepare_value(self, value):
        # Bazadagi 998901234567 → formada "90 123 45 67"
        if isinstance(value, str) and len(value) == 12 and value.startswith("998"):
            return f"{value[3:5]} {value[5:8]} {value[8:10]} {value[10:12]}"
        return value

    def clean(self, value):
        value = super().clean(value)
        if not value and not self.required:
            return ""
        return normalize_phone(value)


class CodeRequestForm(BranchMixin):
    channel = forms.ChoiceField(choices=OneTimeCode.Channel.choices, initial=OneTimeCode.Channel.SMS,
                                widget=forms.RadioSelect, label="Kodni qayerga yuboraylik?", required=False)
    phone = PhoneField()
    remember = forms.BooleanField(label="Meni eslab qol", required=False, initial=True)

    def clean_channel(self):
        return self.cleaned_data.get("channel") or OneTimeCode.Channel.SMS


class CodeVerifyForm(forms.Form):
    code = forms.CharField(label="Tasdiqlash kodi", min_length=6, max_length=6)

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        if not code.isdigit():
            raise ValidationError("Kod faqat raqamlardan iborat.")
        return code


class PasswordLoginForm(BranchMixin):
    phone = PhoneField(label="Login (telefon raqam)")
    password = forms.CharField(label="Parol", strip=False, widget=forms.PasswordInput(
        attrs={"autocomplete": "current-password"}))
    remember = forms.BooleanField(label="Meni eslab qol", required=False, initial=True)


class StyledPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {"old_password": "Joriy parol", "new_password1": "Yangi parol",
                  "new_password2": "Yangi parol (takror)"}
        for name, field in self.fields.items():
            field.label = labels.get(name, field.label)
            field.widget.attrs["class"] = "input"
        self.fields["new_password1"].help_text = "Kamida 10 belgi; faqat raqamlardan iborat bo'lmasin."
