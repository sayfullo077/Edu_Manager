from django import forms


class StyledFormMixin:
    """Dizayn tizimi klasslarini vidjetlarga avtomatik qo'shadi (har formada takrorlamaslik uchun)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput | forms.RadioSelect | forms.HiddenInput):
                continue
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} input".strip()

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                w = self.fields[name].widget
                w.attrs["class"] = f"{w.attrs.get('class', '')} is-invalid".strip()
                w.attrs["aria-invalid"] = "true"


def apply_errors(forms_, error) -> None:
    """Servis ValidationError'ini tegishli forma maydoniga, topilmasa birinchi formaning umumiy xatosiga."""
    forms_ = forms_ if isinstance(forms_, list | tuple) else [forms_]
    by_field = error.message_dict if hasattr(error, "error_dict") else {None: error.messages}
    for field, msgs in by_field.items():
        target = next((f for f in forms_ if field in f.fields), None)
        (target or forms_[0]).add_error(field if target else None, msgs)


def filter_menu(form, active: set[str], groups: dict[str, list[str]] | None = None) -> list[dict]:
    """"Filtr qo'shish" paneli uchun: `form.FILTERS` = [(nom, sarlavha, ikon), ...].

    `groups` — bitta filtr bir nechta maydondan iborat bo'lsa (masalan sana oralig'i: joined → [dan, gacha]).
    Natija `partials/filter_bar.html` ga beriladi.
    """
    groups = groups or {}
    return [{"name": name, "label": label, "icon": icon, "on": name in active,
             "fields": [form[f] for f in groups.get(name, [name])]}
            for name, label, icon in form.FILTERS]
