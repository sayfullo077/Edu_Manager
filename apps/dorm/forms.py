from django import forms

from apps.common.forms import StyledFormMixin
from apps.people.forms import DateInput
from apps.people.models import Gender

from . import selectors
from .models import DormRoom


class ResidentFilterForm(forms.Form):
    """"Hozirda yashayotgan o'quvchilar" filtri (asl tizimdagidek — hammasi bir qatorda)."""

    q = forms.CharField(required=False, max_length=100, widget=forms.TextInput(attrs={
        "placeholder": "Ism, familiya yoki kod bo'yicha qidirish", "type": "search", "aria-label": "Qidiruv"}))
    room = forms.ModelChoiceField(required=False, queryset=None, empty_label="Barcha xonalar")
    gender = forms.ChoiceField(required=False, choices=[("", "Barchasi"), *Gender.choices])
    date_from = forms.DateField(required=False, widget=DateInput(attrs={"aria-label": "Kirgan sana (dan)"}))
    date_to = forms.DateField(required=False, widget=DateInput(attrs={"aria-label": "Kirgan sana (gacha)"}))

    def __init__(self, *args, branch, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["room"].queryset = selectors.room_choices(branch)
        self.fields["room"].widget.attrs["aria-label"] = "Xona"
        self.fields["gender"].widget.attrs["aria-label"] = "Jinsi"
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"

    def to_filters(self) -> selectors.ResidentFilters:
        d = self.cleaned_data if self.is_bound and self.is_valid() else {}
        return selectors.ResidentFilters(q=(d.get("q") or "").strip(), gender=d.get("gender", ""),
                                         room=d["room"].pk if d.get("room") else None,
                                         date_from=d.get("date_from"), date_to=d.get("date_to"))


class RoomFilterForm(forms.Form):
    """Xonalar filtri ("Filtr qo'shish" — asl tizimdagidek: holat, jinsi, xona turi)."""

    FILTERS = [("status", "Holat", "check"), ("gender", "Jinsi", "users"), ("room_type", "Xona turi", "bed")]

    q = forms.CharField(required=False, max_length=60)
    status = forms.ChoiceField(required=False, choices=[("", "Holat"), *DormRoom.Status.choices])
    gender = forms.ChoiceField(required=False, choices=[("", "Jinsi"), *DormRoom.Gender.choices])
    room_type = forms.TypedChoiceField(required=False, coerce=int, empty_value=None,
                                       choices=[("", "Xona turi"), *DormRoom.RoomType.choices])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, label, _ in self.FILTERS:
            self.fields[name].widget.attrs.update({"class": "input", "aria-label": label})

    def active_filters(self) -> set[str]:
        return {name for name, _, _ in self.FILTERS if self.data.get(name)}

    def to_filters(self) -> selectors.RoomFilters:
        d = self.cleaned_data if self.is_bound and self.is_valid() else {}
        return selectors.RoomFilters(q=(d.get("q") or "").strip(), status=d.get("status", ""),
                                     gender=d.get("gender", ""), room_type=d.get("room_type"))


class CheckInForm(StyledFormMixin, forms.Form):
    student = forms.ModelChoiceField(label="O'quvchi", queryset=None, empty_label="— Tanlang —")
    on = forms.DateField(label="Kirgan sana", widget=DateInput())
    note = forms.CharField(label="Izoh", max_length=255, required=False)

    def __init__(self, *args, room, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = selectors.check_in_candidates(room)
        self.fields["student"].label_from_instance = lambda s: (
            f"{s.full_name} · {s.code}" + (f" · {s.school_class.name}" if s.school_class else ""))


class CheckOutForm(forms.Form):
    on = forms.DateField(widget=DateInput())
