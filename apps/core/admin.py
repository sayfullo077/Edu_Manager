from django.contrib import admin

from .models import AcademicYear, Branch, SchoolSettings


@admin.register(SchoolSettings)
class SchoolSettingsAdmin(admin.ModelAdmin):
    list_display = ["name", "short_name", "brand_color"]

    def has_add_permission(self, request):
        return not SchoolSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ["name", "phone", "director_name", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    fieldsets = [
        (None, {"fields": ["name", "address", "phone", "is_active"]}),
        ("Shartnoma rekvizitlari", {"fields": ["director_name", "bank_account", "bank_name", "bank_mfo", "inn"],
                                    "description": "Shartnoma matni va rekvizitlar blokida ko'rsatiladi."}),
    ]


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ["name", "start_date", "end_date", "is_current"]
