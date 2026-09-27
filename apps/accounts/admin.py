from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import OneTimeCode, TelegramLink, User, UserRole


class UserRoleInline(admin.TabularInline):
    model = UserRole
    extra = 1


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["last_name", "first_name"]
    list_display = ["phone", "last_name", "first_name", "is_active", "is_staff"]
    list_filter = ["is_active", "is_staff", "roles__role"]
    search_fields = ["phone", "last_name", "first_name"]
    inlines = [UserRoleInline]
    fieldsets = [
        (None, {"fields": ["phone", "password"]}),
        ("Shaxsiy ma'lumotlar", {"fields": ["last_name", "first_name", "middle_name", "avatar"]}),
        ("Huquqlar", {"fields": ["is_active", "is_staff", "is_superuser", "groups", "user_permissions"]}),
        ("Sanalar", {"fields": ["last_login", "date_joined"]}),
    ]
    add_fieldsets = [
        (None, {"classes": ["wide"], "fields": ["phone", "last_name", "first_name", "password1", "password2"]}),
    ]


@admin.register(TelegramLink)
class TelegramLinkAdmin(admin.ModelAdmin):
    list_display = ["user", "chat_id", "username", "linked_at"]
    search_fields = ["user__phone", "user__last_name", "username"]
    autocomplete_fields = ["user"]


@admin.register(OneTimeCode)
class OneTimeCodeAdmin(admin.ModelAdmin):
    list_display = ["phone", "purpose", "channel", "attempts", "created_at", "expires_at", "used_at"]
    list_filter = ["purpose", "channel"]
    search_fields = ["phone"]
    readonly_fields = [f.name for f in OneTimeCode._meta.fields]

    def has_add_permission(self, request):
        return False
