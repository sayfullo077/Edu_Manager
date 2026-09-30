from django.contrib import admin

from .models import District, Guardian, Mahalla, Student, StudentGuardian, Teacher


class StudentGuardianInline(admin.TabularInline):
    model = StudentGuardian
    extra = 1
    autocomplete_fields = ["guardian", "student"]


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ["code", "last_name", "first_name", "grade", "school_class", "status", "in_erp", "in_emaktab"]
    list_filter = ["status", "school_class", "gender", "in_erp", "in_emaktab"]
    search_fields = ["code", "last_name", "first_name", "phone"]
    list_select_related = ["school_class"]
    readonly_fields = ["code", "created_at", "updated_at"]
    inlines = [StudentGuardianInline]


@admin.register(Guardian)
class GuardianAdmin(admin.ModelAdmin):
    list_display = ["last_name", "first_name", "phone", "status"]
    list_filter = ["status"]
    # Passport/JSHSHIR shifrlangan — bu yerda qidirilmaydi (faqat ism va telefon).
    search_fields = ["last_name", "first_name", "phone"]
    inlines = [StudentGuardianInline]


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ["code", "user", "status", "category", "experience_years"]
    list_filter = ["status", "branch"]
    search_fields = ["code", "user__last_name", "user__first_name", "user__phone"]
    list_select_related = ["user"]
    readonly_fields = ["code"]
    filter_horizontal = ["subjects"]
    autocomplete_fields = ["user"]


class MahallaInline(admin.TabularInline):
    model = Mahalla
    extra = 1
    fields = ["name"]


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ["name", "region", "is_active"]
    list_filter = ["region", "is_active"]
    search_fields = ["name", "region"]
    inlines = [MahallaInline]


@admin.register(Mahalla)
class MahallaAdmin(admin.ModelAdmin):
    list_display = ["name", "district"]
    list_filter = ["district__region"]
    search_fields = ["name", "district__name"]
    autocomplete_fields = ["district"]
