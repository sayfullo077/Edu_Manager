from django.contrib import admin

from .models import Group, GroupMembership, GroupSubject, Room, SchoolClass, Subject


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ["name", "language", "is_active"]
    list_filter = ["language", "is_active"]
    search_fields = ["name"]


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ["name", "branch", "capacity", "is_active"]
    list_filter = ["branch", "is_active"]


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "grade", "language", "homeroom_teacher", "academic_year", "is_active"]
    list_filter = ["academic_year", "kind", "language", "is_active"]
    search_fields = ["name"]
    list_select_related = ["homeroom_teacher__user", "academic_year"]
    autocomplete_fields = ["homeroom_teacher"]


class GroupSubjectInline(admin.TabularInline):
    model = GroupSubject
    extra = 1
    autocomplete_fields = ["subject", "teacher"]


class GroupMembershipInline(admin.TabularInline):
    model = GroupMembership
    extra = 0
    autocomplete_fields = ["student"]


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ["code", "school_class", "kind", "pay_scheme", "rate", "deduction_percent", "is_active"]
    list_filter = ["academic_year", "kind", "pay_scheme", "is_active"]
    search_fields = ["code"]
    list_select_related = ["school_class"]
    inlines = [GroupSubjectInline, GroupMembershipInline]
