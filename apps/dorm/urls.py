from django.urls import path

from . import views

app_name = "dorm"

urlpatterns = [
    path("dorm/", views.dashboard, name="dashboard"),
    path("dorm/residents/export/", views.residents_export, name="residents_export"),
    path("dorm/rooms/", views.room_list, name="room_list"),
    path("dorm/rooms/export/", views.room_export, name="room_export"),
    path("dorm/rooms/<int:pk>/", views.room_detail, name="room_detail"),
    path("dorm/stays/<int:pk>/check-out/", views.stay_check_out, name="stay_check_out"),
]
