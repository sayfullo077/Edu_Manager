from django.contrib import admin

from .models import PayrollSettings, Penalty, SalaryPayment


@admin.register(PayrollSettings)
class PayrollSettingsAdmin(admin.ModelAdmin):
    list_display = ("branch", "second_category_percent", "certificate_percent", "language_percent", "homeroom_rate")


class ReadOnlyAdmin(admin.ModelAdmin):
    """Moliyaviy yozuvlar (jarima, oylik to'lovi) faqat servis orqali — admin'da faqat ko'rish, iz qoldirmay
    o'zgartirib yoki o'chirib bo'lmaydi (jarima — bekor qilinadi, to'lov — kassa chiqimi bilan bog'langan)."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Penalty)
class PenaltyAdmin(ReadOnlyAdmin):
    list_display = ("teacher", "month", "amount", "reason", "created_by", "cancelled_at")
    list_filter = ("month",)


@admin.register(SalaryPayment)
class SalaryPaymentAdmin(ReadOnlyAdmin):
    list_display = ("teacher", "month", "kind", "amount", "paid_on", "created_by")
    list_filter = ("month", "kind")
