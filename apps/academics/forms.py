from django import forms

from apps.common.forms import StyledFormMixin
from apps.core.models import AcademicYear

from . import selectors
from .models import Group, Language, SchoolClass, Subject, TimeSlot, Weekday
from .services.groups import SubjectTeacher


class ClassFilterForm(forms.Form):
    """Sinflar va guruhlar filtri. O'quv yili sukut bo'yicha joriy (view qo'yadi)."""

    FILTERS = [("year", "O'quv yili", "calendar"), ("kind", "Turi", "school"), ("language", "Ta'lim tili", "book")]

    q = forms.CharField(required=False, max_length=60)
    year = forms.ModelChoiceField(required=False, queryset=AcademicYear.objects.order_by("-start_date"),
                                  empty_label="Barcha yillar")
    kind = forms.ChoiceField(required=False, choices=[("", "Barcha turlar"), *SchoolClass.Kind.choices])
    language = forms.ChoiceField(required=False, choices=[("", "Barcha tillar"), *Language.choices])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {name: label for name, label, _ in self.FILTERS}
        for name in labels:
            self.fields[name].widget.attrs.update({"class": "input", "aria-label": labels[name]})
        self.fields["year"].widget.attrs["data-keep-empty"] = ""  # "Barcha yillar" ham yuborilsin

    def active_filters(self) -> set[str]:
        return {name for name, _, _ in self.FILTERS if self.data.get(name)}

    def to_filters(self) -> selectors.ClassFilters:
        d = self.cleaned_data if self.is_bound and self.is_valid() else {}
        return selectors.ClassFilters(year=d["year"].pk if d.get("year") else None, kind=d.get("kind", ""),
                                      language=d.get("language", ""), q=(d.get("q") or "").strip())


class SchoolClassForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SchoolClass
        fields = ["academic_year", "name", "kind", "grade", "language", "homeroom_teacher", "room", "capacity",
                  "monthly_tariff", "is_active"]
        widgets = {"kind": forms.RadioSelect, "language": forms.RadioSelect,
                   "monthly_tariff": forms.NumberInput(attrs={"step": "1000", "min": "0"})}
        labels = {"grade": "Daraja (1–11)", "monthly_tariff": "Oylik tarif (chegirmasiz, so'm)",
                  "capacity": "Sig'imi (o'quvchi)"}
        help_texts = {"name": "Masalan: 3-B yoki Aniq1", "grade": "Yo'nalish uchun bo'sh qoldiring"}

    def __init__(self, *args, branch, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["academic_year"].queryset = selectors.year_choices()
        self.fields["academic_year"].empty_label = None
        self.fields["homeroom_teacher"].queryset = selectors.teacher_choices(branch)
        self.fields["homeroom_teacher"].empty_label = "— Biriktirilmagan —"
        self.fields["room"].queryset = selectors.room_choices(branch)
        self.fields["room"].empty_label = "— Tanlanmagan —"
        for name in ("kind", "language"):
            self.fields[name].choices = [c for c in self.fields[name].choices if c[0]]
        self.fields["is_active"].label = "Faol (qabul va ro'yxatlarda ko'rinadi)"


class GroupForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Group
        fields = ["school_class", "code", "kind", "level", "pay_scheme", "rate", "deduction_percent", "room",
                  "capacity", "is_active"]
        widgets = {"kind": forms.RadioSelect(attrs={"data-group-kind": ""}),
                   "pay_scheme": forms.RadioSelect,
                   "rate": forms.NumberInput(attrs={"step": "100", "min": "0", "data-group-rate": ""}),
                   "deduction_percent": forms.NumberInput(attrs={"step": "0.5", "min": "0", "max": "100"})}
        labels = {"school_class": "Sinf / yo'nalish", "rate": "Stavka (so'm)", "capacity": "Sig'imi (o'quvchi)"}

    def __init__(self, *args, branch, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["school_class"].queryset = selectors.class_choices(branch)
        self.fields["school_class"].label_from_instance = lambda c: f"{c.name} · {c.academic_year.name}"
        self.fields["school_class"].empty_label = "— Tanlang —"
        self.fields["room"].queryset = selectors.room_choices(branch)
        self.fields["room"].empty_label = "— Tanlanmagan —"
        for name in ("kind", "pay_scheme"):
            self.fields[name].choices = [c for c in self.fields[name].choices if c[0]]
        self.fields["is_active"].label = "Faol"


class SubjectTeacherForm(StyledFormMixin, forms.Form):
    """Guruhdagi bitta fan va uning o'qituvchisi. Bo'sh qator e'tiborsiz qoldiriladi."""

    subject = forms.ModelChoiceField(label="Fan", queryset=None, required=False, empty_label="— Fan —")
    teacher = forms.ModelChoiceField(label="O'qituvchi", queryset=None, required=False,
                                     empty_label="— O'qituvchi —")
    hours = forms.IntegerField(label="Haftalik soat", required=False, min_value=0, max_value=20,
                               widget=forms.NumberInput(attrs={"min": 0, "max": 20}))

    def __init__(self, *args, branch, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["subject"].queryset = selectors.subject_choices()
        self.fields["subject"].label_from_instance = lambda s: f"{s.name} ({s.get_language_display()})"
        self.fields["teacher"].queryset = selectors.teacher_choices(branch)

    def clean(self):
        d = super().clean()
        if bool(d.get("subject")) != bool(d.get("teacher")):
            raise forms.ValidationError("Fan va o'qituvchini birga tanlang.")
        return d


SUBJECT_ROWS = 3  # bir guruhda odatda 1–2 fan ("Birlashma") — bo'sh qatorlar e'tiborsiz


def subject_forms(data, *, branch, group: Group | None = None) -> list[SubjectTeacherForm]:
    initial = [{"subject": gs.subject_id, "teacher": gs.teacher_id, "hours": gs.hours_per_week}
               for gs in group.subjects.all()] if group else []
    rows = max(SUBJECT_ROWS, len(initial) + 1)
    return [SubjectTeacherForm(data, prefix=f"st{i}", branch=branch,
                               initial=initial[i] if i < len(initial) else None) for i in range(rows)]


def subject_pairs(forms_: list[SubjectTeacherForm]) -> list[SubjectTeacher]:
    return [SubjectTeacher(f.cleaned_data["subject"], f.cleaned_data["teacher"], f.cleaned_data.get("hours") or 0)
            for f in forms_ if f.cleaned_data.get("subject")]


class MembersForm(forms.Form):
    """Tanlov guruhiga o'quvchilar qo'shish (ro'yxatdan belgilanadi)."""

    students = forms.ModelMultipleChoiceField(queryset=None, widget=forms.CheckboxSelectMultiple,
                                              error_messages={"required": "Kamida bitta o'quvchini belgilang."})
    on = forms.DateField(label="Qo'shilgan sana", widget=forms.DateInput(attrs={"type": "date", "class": "input"},
                                                                       format="%Y-%m-%d"))

    def __init__(self, *args, candidates, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["students"].queryset = candidates
        self.fields["students"].label_from_instance = lambda s: (
            f"{s.full_name} · {s.school_class.name}" if s.school_class else s.full_name)


# ---------- Dars jadvali ----------

class TimetableFilterForm(forms.Form):
    """Kimning jadvali: sinf, o'qituvchi yoki xona; qaysi hafta (istalgan kun — o'sha hafta)."""

    VIEWS = [("class", "Sinf"), ("teacher", "O'qituvchi"), ("room", "Xona")]

    by = forms.ChoiceField(choices=VIEWS, required=False)
    year = forms.ModelChoiceField(label="O'quv yili", queryset=AcademicYear.objects.order_by("-start_date"),
                                  required=False, empty_label=None)
    school_class = forms.ModelChoiceField(label="Sinf", queryset=None, required=False, empty_label="— Tanlang —")
    teacher = forms.ModelChoiceField(label="O'qituvchi", queryset=None, required=False, empty_label="— Tanlang —")
    room = forms.ModelChoiceField(label="Xona", queryset=None, required=False, empty_label="— Tanlang —")
    week = forms.DateField(required=False)

    def __init__(self, *args, branch, year, **kwargs):
        super().__init__(*args, **kwargs)
        targets = selectors.timetable_targets(branch, year)
        self.fields["school_class"].queryset = targets["classes"]
        self.fields["teacher"].queryset = targets["teachers"]
        self.fields["room"].queryset = targets["rooms"]
        for name in ("year", "school_class", "teacher", "room"):
            self.fields[name].widget.attrs["class"] = "input"


class LessonForm(StyledFormMixin, forms.Form):
    """Katakka dars qo'shish: guruh → fan (o'qituvchisi guruhdan), xona, qaysi sanadan."""

    weekday = forms.TypedChoiceField(choices=Weekday.choices, coerce=int, widget=forms.HiddenInput)
    slot = forms.ModelChoiceField(queryset=None, widget=forms.HiddenInput)
    group = forms.ModelChoiceField(label="Guruh", queryset=None, empty_label="— Guruhni tanlang —")
    subject = forms.ModelChoiceField(label="Fan (o'qituvchi guruhdan olinadi)", queryset=None,
                                     empty_label="— Fan —")
    room = forms.ModelChoiceField(label="Xona", queryset=None, required=False, empty_label="— Guruh xonasi —")
    on = forms.DateField(label="Qaysi sanadan", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
                         help_text="Shu sanadan oldingi haftalar o'zgarmaydi.")

    def __init__(self, *args, branch, groups, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slot"].queryset = TimeSlot.objects.filter(branch=branch)
        self.fields["group"].queryset = groups
        self.fields["group"].label_from_instance = lambda g: f"{g.code} · {g.school_class.name}"
        self.fields["group"].widget.attrs["data-lesson-group"] = ""
        self.fields["subject"].queryset = Subject.objects.filter(groupsubject__group__in=groups).distinct()
        self.fields["subject"].widget.attrs["data-lesson-subject"] = ""
        self.fields["room"].queryset = selectors.room_choices(branch)

    def clean(self):
        d = super().clean()
        if d.get("group") and d.get("subject") and not d["group"].subjects.filter(subject=d["subject"]).exists():
            self.add_error("subject", "Bu fan tanlangan guruhda yo'q.")
        return d


class RemoveLessonForm(forms.Form):
    on = forms.DateField(label="Qaysi sanadan olib tashlansin",
                         widget=forms.DateInput(attrs={"type": "date", "class": "input"}, format="%Y-%m-%d"))


MAX_SLOTS = 10


class BellsForm(forms.Form):
    """Qo'ng'iroqlar: 1..MAX_SLOTS dars uchun boshlanish/tugash. Bo'sh qator — o'sha dars yo'q."""

    def __init__(self, *args, slots, **kwargs):
        super().__init__(*args, **kwargs)
        by_number = {s.number: s for s in slots}
        for n in range(1, MAX_SLOTS + 1):
            s = by_number.get(n)
            for part in ("start", "end"):
                self.fields[f"s{n}_{part}"] = forms.TimeField(
                    required=False, initial=getattr(s, part) if s else None,
                    widget=forms.TimeInput(attrs={"type": "time", "class": "input"}, format="%H:%M"))
            self.fields[f"s{n}_break"] = forms.BooleanField(required=False, initial=bool(s and s.is_break))

    def rows(self):
        return [(n, self[f"s{n}_start"], self[f"s{n}_end"], self[f"s{n}_break"]) for n in range(1, MAX_SLOTS + 1)]

    def slot_rows(self):
        from .services.timetable import SlotRow
        d = self.cleaned_data
        return [SlotRow(n, d.get(f"s{n}_start"), d.get(f"s{n}_end"), bool(d.get(f"s{n}_break")))
                for n in range(1, MAX_SLOTS + 1)]
