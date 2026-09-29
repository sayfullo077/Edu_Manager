from datetime import datetime, time
from decimal import Decimal

from django import forms
from django.utils import timezone

from apps.academics.models import SchoolClass
from apps.common.forms import StyledFormMixin
from apps.core.models import AcademicYear
from apps.people.forms import DateInput
from apps.people.models import Student

from . import selectors
from .models import Account, ExpenseCategory, Payment, Transaction, Withdrawal

MONEY_ATTRS = {"inputmode": "numeric", "min": "0", "step": "1000", "autocomplete": "off"}


class PaymentForm(StyledFormMixin, forms.Form):
    amount = forms.DecimalField(label="Summa (so'm)", min_value=Decimal("1"), max_digits=14, decimal_places=0,
                                widget=forms.NumberInput(attrs=MONEY_ATTRS))
    method = forms.ChoiceField(label="To'lov usuli", choices=Payment.Method.choices, widget=forms.RadioSelect,
                               initial=Payment.Method.CASH)
    card_network = forms.ChoiceField(label="Karta turi", required=False,
                                     choices=[("", "—"), *Payment.CardNetwork.choices])
    payer_name = forms.CharField(label="To'lovchi (ixtiyoriy)", max_length=120, required=False)
    paid_on = forms.DateField(label="Sana", required=False, widget=DateInput(),
                              help_text="Bo'sh — bugun. Karta/o'tkazmani oldingi sana bilan kiritish mumkin")
    note = forms.CharField(label="Izoh", max_length=255, required=False,
                           widget=forms.TextInput(attrs={"placeholder": "Ixtiyoriy"}))

    def payment_kwargs(self) -> dict:
        """Servis argumentlari: sana bugun bo'lmasa — o'sha kunning tushi (vaqt zonasi bilan)."""
        d = dict(self.cleaned_data)
        paid_on = d.pop("paid_on", None)
        if paid_on and paid_on != timezone.localdate():
            d["paid_at"] = timezone.make_aware(datetime.combine(paid_on, time(12, 0)))
        return d


class ReverseForm(StyledFormMixin, forms.Form):
    reason = forms.CharField(label="Storno sababi", max_length=255)


class CashCloseForm(StyledFormMixin, forms.Form):
    counted = forms.DecimalField(label="Kassada sanalgan naqd (so'm)", min_value=Decimal("0"), max_digits=14,
                                 decimal_places=0, widget=forms.NumberInput(attrs=MONEY_ATTRS))
    note = forms.CharField(label="Izoh", max_length=255, required=False)


class ExpenseForm(StyledFormMixin, forms.Form):
    category = forms.ModelChoiceField(label="Kategoriya", queryset=ExpenseCategory.objects.filter(is_active=True),
                                      empty_label=None)
    amount = forms.DecimalField(label="Summa (so'm)", min_value=Decimal("1"), max_digits=14, decimal_places=0,
                                widget=forms.NumberInput(attrs=MONEY_ATTRS))
    account_kind = forms.ChoiceField(label="Qayerdan", choices=[(Account.Kind.CASH, "Naqd kassa"),
                                                                 (Account.Kind.BANK, "Bank hisobi")],
                                     widget=forms.RadioSelect, initial=Account.Kind.CASH)
    spent_at = forms.DateField(label="Sana", widget=DateInput(), initial=timezone.localdate)
    description = forms.CharField(label="Izoh (nima uchun)", max_length=255)


class BudgetLimitForm(forms.Form):
    """Har bir kategoriya uchun bitta maydon: limit_<id>."""

    def __init__(self, *args, rows, **kwargs):
        super().__init__(*args, **kwargs)
        for row in rows:
            self.fields[f"limit_{row.category.pk}"] = forms.DecimalField(
                label=row.category.name, min_value=Decimal("0"), max_digits=14, decimal_places=0,
                initial=row.limit, widget=forms.NumberInput(attrs={**MONEY_ATTRS, "class": "input"}))


class WithdrawalDatesForm(StyledFormMixin, forms.Form):
    """Chiqish sanalari — o'zgarganda hisob-kitob qayta ko'rsatiladi (GET)."""

    left_on = forms.DateField(label="O'qishdan chiqqan sana", widget=DateInput(attrs={"data-autosubmit": ""}),
                              help_text="Shu kun ham o'qigan kun sifatida hisoblanadi")
    dorm_left_on = forms.DateField(label="Yotoqxonadan chiqqan sana", required=False,
                                   widget=DateInput(attrs={"data-autosubmit": ""}),
                                   help_text="Bo'sh bo'lsa — maktabdan chiqqan sana")


class WithdrawalForm(WithdrawalDatesForm):
    reason = forms.ChoiceField(label="Sababi", choices=[("", "— Tanlang —"), *Withdrawal.Reason.choices])
    note = forms.CharField(label="Izoh", max_length=255, required=False,
                           widget=forms.TextInput(attrs={"placeholder": "Masalan: qaysi maktabga ko'chdi"}))
    refund_method = forms.ChoiceField(label="Ortiqcha pulni qaytarish", required=False, widget=forms.RadioSelect,
                                      choices=Withdrawal.RefundMethod.choices)
    expected_refund = forms.DecimalField(widget=forms.HiddenInput, max_digits=14, decimal_places=2)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("left_on", "dorm_left_on"):
            self.fields[name].widget = forms.HiddenInput()


class MonthInput(forms.DateInput):
    input_type = "month"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m", **kwargs)


class ScheduleForm(StyledFormMixin, forms.Form):
    """"Grafik" oynasi: keyingi oylarni oldindan yaratish (oldindan to'lov uchun)."""

    start_month = forms.DateField(label="Boshlanish oyi", input_formats=["%Y-%m"], widget=MonthInput())
    months = forms.TypedChoiceField(label="Nechta oy", coerce=int)
    due_date = forms.DateField(label="Muddat kuni", required=False, widget=DateInput(),
                               help_text="Bo'sh qoldirilsa har oy uchun avtomatik 10-sana. "
                                         "Tanlangan sananing kuni har bir oyga qo'llanadi.")

    def __init__(self, *args, max_months: int = 12, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["months"].choices = [(n, f"{n} oy") for n in range(1, min(12, max_months) + 1)]

    @classmethod
    def for_contract(cls, contract, missing_months):
        """Kartadagi bo'sh forma — keyingi yaratilmagan oydan boshlab. Yaratiladigan oy yo'q bo'lsa None."""
        if not contract or not missing_months:
            return None
        return cls(max_months=len(missing_months), initial={"start_month": missing_months[0], "months": 1})


class PaymentFilterForm(forms.Form):
    """To'lovlar ro'yxati filtri (asl tizimdagidek — hammasi doim ko'rinadi). Sana bo'sh bo'lsa — bugun."""

    q = forms.CharField(required=False, max_length=100, label="O'quvchi ismi, kodi yoki izoh",
                        widget=forms.TextInput(attrs={"placeholder": "O'quvchi ismi, kodi yoki izoh…",
                                                      "type": "search"}))
    date_from = forms.DateField(required=False, label="Sanadan", widget=DateInput())
    date_to = forms.DateField(required=False, label="Sanagacha", widget=DateInput())
    method = forms.ChoiceField(required=False, label="To'lov turi", choices=[("", "Barchasi"), *Payment.Method.choices])
    school_class = forms.ModelChoiceField(required=False, label="Sinf", queryset=None, empty_label="Barchasi")
    received_by = forms.ModelChoiceField(required=False, label="Yaratuvchi", queryset=None, empty_label="Barchasi")

    def __init__(self, *args, branch, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["school_class"].queryset = (SchoolClass.objects.filter(branch=branch, is_active=True)
                                                .order_by("kind", "grade", "name"))
        self.fields["received_by"].queryset = selectors.payment_receivers(branch)
        self.fields["received_by"].label_from_instance = lambda u: u.full_name
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"

    def to_filters(self) -> selectors.PaymentFilters:
        today = timezone.localdate()
        if not self.is_bound:  # sahifa birinchi ochilganda — bugungi to'lovlar
            return selectors.PaymentFilters(date_from=today, date_to=today)
        if not self.is_valid():
            return selectors.PaymentFilters(date_from=today, date_to=today)
        d = self.cleaned_data
        return selectors.PaymentFilters(
            q=d["q"].strip(), date_from=d["date_from"], date_to=d["date_to"], method=d["method"],
            school_class=d["school_class"].pk if d["school_class"] else None,
            received_by=d["received_by"].pk if d["received_by"] else None)


class TransactionFilterForm(forms.Form):
    """Tranzaksiyalar filtri (asl tizimdagidek). Sana bo'sh bo'lsa — bugun."""

    q = forms.CharField(required=False, max_length=100, label="Qidiruv",
                        widget=forms.TextInput(attrs={"placeholder": "Izoh, kvitansiya yoki ID (TRX-…)",
                                                      "type": "search"}))
    direction = forms.ChoiceField(required=False, label="Turi",
                                  choices=[("", "Barchasi"), *Transaction.Direction.choices])
    # Kategoriya va to'lov turi — bir nechtasini birdan tanlash mumkin (asl tizimdagidek)
    category = forms.MultipleChoiceField(required=False, label="Kategoriya", choices=selectors.TRANSACTION_CATEGORIES)
    account_kind = forms.MultipleChoiceField(required=False, label="To'lov turi", choices=[
        (Account.Kind.CASH, "Naqd"), (Account.Kind.TERMINAL, "Terminal"), (Account.Kind.BANK, "Bank")])
    card_network = forms.ChoiceField(required=False, label="Karta tarmog'i",
                                     choices=[("", "Barchasi"), *Payment.CardNetwork.choices])
    status = forms.ChoiceField(required=False, label="Status", choices=[
        ("", "Barchasi"), ("ok", "Muvaffaqiyatli"), ("cancelled", "Bekor qilingan"), ("storno", "Storno")])
    created_by = forms.ModelChoiceField(required=False, label="Yaratuvchi", queryset=None, empty_label="Barchasi")
    date_from = forms.DateField(required=False, label="Boshlanish", widget=DateInput())
    date_to = forms.DateField(required=False, label="Tugash", widget=DateInput())
    min_amount = forms.DecimalField(required=False, label="Summa (dan)", min_value=0, max_digits=14,
                                    decimal_places=0, widget=forms.NumberInput(attrs={**MONEY_ATTRS,
                                                                                      "placeholder": "0"}))

    def __init__(self, *args, branch, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["created_by"].queryset = selectors.transaction_creators(branch)
        self.fields["created_by"].label_from_instance = lambda u: u.full_name
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"

    def to_filters(self) -> selectors.TransactionFilters:
        today = timezone.localdate()
        if not self.is_bound or not self.is_valid():
            return selectors.TransactionFilters(date_from=today, date_to=today)
        d = self.cleaned_data
        return selectors.TransactionFilters(
            q=d["q"], direction=d["direction"], categories=tuple(d["category"]),
            account_kinds=tuple(d["account_kind"]),
            card_network=d["card_network"], status=d["status"],
            created_by=d["created_by"].pk if d["created_by"] else None,
            date_from=d["date_from"], date_to=d["date_to"], min_amount=d["min_amount"])


class PeriodForm(forms.Form):
    """Sana oralig'i (Bank hisobi va h.k.). Bo'sh bo'lsa — oy boshidan bugungacha."""

    date_from = forms.DateField(required=False, label="Boshlanish sanasi", widget=DateInput(attrs={"class": "input"}))
    date_to = forms.DateField(required=False, label="Tugash sanasi", widget=DateInput(attrs={"class": "input"}))

    def period(self) -> tuple:
        today = timezone.localdate()
        d = self.cleaned_data if self.is_bound and self.is_valid() else {}
        date_from = d.get("date_from") or today.replace(day=1)
        date_to = d.get("date_to") or today
        return (date_to, date_from) if date_from > date_to else (date_from, date_to)


class InvoiceFilterForm(forms.Form):
    """To'lov grafiklari filtri ("Filtr qo'shish" menyusi — asl tizimdagidek)."""

    FILTERS = [("school_class", "Sinf", "school"), ("academic_year", "O'quv yili", "calendar"),
               ("month", "Oy", "calendar"), ("state", "Holati", "check"),
               ("student_status", "O'quvchi holati", "users")]
    STATES = [("", "Holati"), ("pending", "Kutilmoqda"), ("partial", "Qisman"), ("paid", "To'langan"),
              ("overdue", "Muddati o'tgan"), ("waived", "Kechirilgan"), ("cancelled", "Bekor qilingan")]

    q = forms.CharField(required=False, max_length=100)
    school_class = forms.ModelChoiceField(required=False, queryset=None, empty_label="Barcha sinflar")
    academic_year = forms.ModelChoiceField(required=False, queryset=None, empty_label="Barcha yillar")
    month = forms.DateField(required=False, input_formats=["%Y-%m"], widget=MonthInput())
    state = forms.ChoiceField(required=False, choices=STATES)
    student_status = forms.ChoiceField(required=False, choices=[("", "O'quvchi holati"), *Student.Status.choices])

    def __init__(self, *args, branch, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["school_class"].queryset = (SchoolClass.objects.filter(branch=branch, is_active=True)
                                                .order_by("kind", "grade", "name"))
        self.fields["academic_year"].queryset = AcademicYear.objects.order_by("-start_date")
        labels = {name: label for name, label, _ in self.FILTERS}
        for name, field in self.fields.items():
            if name != "q":
                field.widget.attrs.update({"class": "input", "aria-label": labels.get(name, "")})

    def active_filters(self) -> set[str]:
        return {name for name, _, _ in self.FILTERS if self.data.get(name)}

    def to_filters(self) -> selectors.InvoiceFilters:
        d = self.cleaned_data if self.is_bound and self.is_valid() else {}
        return selectors.InvoiceFilters(
            q=(d.get("q") or "").strip(), month=d.get("month"), state=d.get("state", ""),
            student_status=d.get("student_status", ""),
            school_class=d["school_class"].pk if d.get("school_class") else None,
            academic_year=d["academic_year"].pk if d.get("academic_year") else None)



class DebtorFilterForm(InvoiceFilterForm):
    """Qarzdorlar filtri: sinf, o'quv yili, oy, holat (asl tizimdagidek)."""

    FILTERS = [("school_class", "Sinf", "school"), ("academic_year", "O'quv yili", "calendar"),
               ("month", "Oy", "calendar"), ("state", "Holat", "check")]
    STATES = [("", "Holat"), ("overdue", "Muddati o'tgan"), ("partial", "Qisman to'langan"),
              ("pending", "Muddati kelmagan")]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["state"].choices = self.STATES
        del self.fields["student_status"]
