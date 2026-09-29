from django.db import models

from . import crypto


class EncryptedCharField(models.TextField):
    """Bazada shifrlangan holda saqlanadi, Python'da oddiy satr sifatida ishlatiladi.

    Eslatma: bu maydon bo'yicha filter/order qilib bo'lmaydi — qidirish uchun yonidagi
    `*_index` (blind index) maydonidan foydalaning.
    """

    def __init__(self, *args, max_length=None, **kwargs):
        self.plain_max_length = max_length
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self.plain_max_length:
            kwargs["max_length"] = self.plain_max_length
        return name, path, args, kwargs

    def from_db_value(self, value, expression, connection):
        if not value:
            return value
        return crypto.decrypt(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value:
            return value
        return crypto.encrypt(value)

    def formfield(self, **kwargs):
        from django import forms
        return super().formfield(**{"form_class": forms.CharField, "max_length": self.plain_max_length,
                                    "widget": forms.TextInput, **kwargs})
