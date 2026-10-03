from django.urls import path

from . import views

app_name = "director"

urlpatterns = [
    path("finance/", views.finance_report, name="finance_report"),
    path("attendance/", views.attendance_report, name="attendance_report"),
    path("staff/", views.staff, name="staff"),
    path("staff/<int:pk>/toggle/", views.staff_toggle, name="staff_toggle"),
]
