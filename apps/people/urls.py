from django.urls import path

from . import views

app_name = "people"

urlpatterns = [
    path("students/", views.student_list, name="student_list"),
    path("students/new/", views.student_create, name="student_create"),
    path("students/export/", views.student_export, name="student_export"),
    path("students/print/", views.student_print, name="student_print"),
    path("students/<int:pk>/delete/", views.student_delete, name="student_delete"),
    path("students/<int:pk>/", views.student_detail, name="student_detail"),
    path("students/<int:pk>/edit/", views.student_update, name="student_update"),
    path("students/<int:pk>/toggle/<str:field>/", views.student_toggle_flag, name="student_toggle_flag"),
    path("students/<int:pk>/guardians/add/", views.student_add_guardian, name="student_add_guardian"),
    path("students/<int:pk>/guardians/<int:link_pk>/primary/", views.student_set_primary_guardian,
         name="student_set_primary_guardian"),
    path("students/<int:pk>/guardians/<int:link_pk>/detach/", views.student_detach_guardian,
         name="student_detach_guardian"),
    path("teachers/", views.teacher_list, name="teacher_list"),
    path("teachers/new/", views.teacher_create, name="teacher_create"),
    path("teachers/<int:pk>/", views.teacher_detail, name="teacher_detail"),
    path("teachers/<int:pk>/edit/", views.teacher_update, name="teacher_update"),
    path("teachers/<int:pk>/status/", views.teacher_set_status, name="teacher_set_status"),
    path("address/mahallas/", views.address_mahallas, name="address_mahallas"),
    path("guardians/", views.guardian_list, name="guardian_list"),
    path("guardians/<int:pk>/", views.guardian_detail, name="guardian_detail"),
    path("guardians/export/", views.guardian_export, name="guardian_export"),
]
