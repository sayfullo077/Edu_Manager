from django.urls import path

from . import views

app_name = "dorm"

urlpatterns = [
    path("dorm/", views.dashboard, name="dashboard"),
    path("dorm/residents/export/", views.residents_export, name="residents_export"),
    path("dorm/rooms/", views.room_list, name="room_list"),
    path("dorm/rooms/export/", views.room_export, name="room_export"),
    path("dorm/rooms/<int:pk>/", views.room_detail, name="room_detail"),
    path("dorm/invoices/", views.invoice_list, name="invoice_list"),
    path("dorm/invoices/export/", views.invoice_export, name="invoice_export"),
    path("dorm/debtors/", views.debtor_list, name="debtor_list"),
    path("dorm/debtors/export/", views.debtor_export, name="debtor_export"),
    path("dorm/attendance/", views.attendance, name="attendance"),
    path("dorm/attendance/export/", views.attendance_export, name="attendance_export"),
    path("dorm/attendance/mark/", views.attendance_mark, name="attendance_mark"),
    path("dorm/attendance/day/", views.attendance_day, name="attendance_day"),
    path("dorm/stays/<int:pk>/check-out/", views.stay_check_out, name="stay_check_out"),
]
