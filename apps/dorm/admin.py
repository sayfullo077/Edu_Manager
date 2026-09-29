from django.contrib import admin

from .models import DormRoom, DormStay


@admin.register(DormRoom)
class DormRoomAdmin(admin.ModelAdmin):
    list_display = ("name", "floor", "branch", "room_type", "gender", "capacity", "monthly_fee", "status")
    list_filter = ("branch", "gender", "room_type", "status")
    search_fields = ("name",)


@admin.register(DormStay)
class DormStayAdmin(admin.ModelAdmin):
    list_display = ("student", "room", "checked_in", "checked_out")
    list_filter = ("room", "checked_out")
    search_fields = ("student__last_name", "student__first_name", "student__code")
    raw_id_fields = ("student",)
