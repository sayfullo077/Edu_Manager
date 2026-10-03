from django.urls import path

from . import views

app_name = "academics"

urlpatterns = [
    path("classes/", views.class_list, name="class_list"),
    path("classes/new/", views.class_create, name="class_create"),
    path("classes/<int:pk>/", views.class_detail, name="class_detail"),
    path("classes/<int:pk>/edit/", views.class_update, name="class_update"),
    path("classes/<int:pk>/delete/", views.class_delete, name="class_delete"),
    path("classes/groups/new/", views.group_create, name="group_create"),
    path("classes/groups/<int:pk>/", views.group_detail, name="group_detail"),
    path("classes/groups/<int:pk>/edit/", views.group_update, name="group_update"),
    path("classes/groups/<int:pk>/delete/", views.group_delete, name="group_delete"),
    path("classes/groups/<int:pk>/members/add/", views.group_add_members, name="group_add_members"),
    path("classes/groups/<int:pk>/members/<int:member_pk>/remove/", views.group_remove_member,
         name="group_remove_member"),
    path("timetable/", views.timetable_view, name="timetable"),
    path("timetable/print/", views.timetable_print, name="timetable_print"),
    path("timetable/bells/", views.bells, name="bells"),
    path("timetable/export/", views.timetable_export, name="timetable_export"),
    path("timetable/export/all/", views.timetable_export_all, name="timetable_export_all"),
    path("timetable/lessons/place/", views.lesson_place, name="lesson_place"),
    path("timetable/lessons/<int:pk>/move/", views.lesson_move, name="lesson_move"),
    path("timetable/lessons/new/", views.lesson_panel_new, name="lesson_panel_new"),
    path("timetable/lessons/add/", views.lesson_create, name="lesson_create"),
    path("timetable/lessons/<int:pk>/", views.lesson_panel, name="lesson_panel"),
    path("my/schedule/", views.my_schedule, name="my_schedule"),
    path("my/groups/", views.my_groups, name="my_groups"),
    path("my/homeroom/", views.my_homeroom, name="my_homeroom"),
    path("my/salary-guide/", views.my_salary_guide, name="my_salary_guide"),
    path("my/homeroom/<int:pk>/", views.my_homeroom_class, name="my_homeroom_class"),
    path("my/homeroom/<int:pk>/export/", views.my_homeroom_export, name="my_homeroom_export"),
    path("my/groups/<int:pk>/", views.my_group_detail, name="my_group_detail"),
    path("my/groups/<int:pk>/add/", views.my_group_add, name="my_group_add"),
    path("my/groups/<int:pk>/remove/<int:membership_pk>/", views.my_group_remove, name="my_group_remove"),
    path("timetable/lessons/<int:pk>/remove/", views.lesson_remove, name="lesson_remove"),
]
