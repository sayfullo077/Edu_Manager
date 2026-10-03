from django.urls import path

from . import views

app_name = "payroll"

urlpatterns = [
    path("", views.payroll_list, name="list"),
    path("my/", views.my_salary, name="my_salary"),
    path("export/", views.payroll_export, name="export"),
    path("settings/", views.payroll_settings, name="settings"),
    path("teachers/<int:pk>/", views.payroll_teacher, name="teacher"),
    path("teachers/<int:pk>/export/", views.payroll_teacher_export, name="teacher_export"),
    path("teachers/<int:pk>/pay/", views.salary_pay, name="salary_pay"),
    path("teachers/<int:pk>/penalties/", views.penalty_add, name="penalty_add"),
    path("penalties/<int:pk>/cancel/", views.penalty_cancel, name="penalty_cancel"),
]
