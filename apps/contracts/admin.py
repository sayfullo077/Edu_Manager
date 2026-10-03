from django.contrib import admin

from .models import Contract, ContractTemplate


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ["number", "student", "class_name", "monthly_fee", "status", "academic_year", "created_at"]
    list_filter = ["status", "academic_year", "branch"]
    search_fields = ["number", "student__last_name", "student__first_name", "student__code"]
    list_select_related = ["student", "academic_year"]
    # Holat faqat servis orqali o'zgaradi (SMS tasdiqlash) — admin'da qo'lda "imzolangan" qilib bo'lmaydi.
    readonly_fields = ["number", "status", "monthly_fee", "sent_at", "signed_at", "signed_phone", "cancelled_at",
                       "created_by", "created_at", "updated_at"]
    autocomplete_fields = ["student", "guardian"]


@admin.register(ContractTemplate)
class ContractTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "is_default", "updated_at"]
    list_filter = ["is_active"]
