from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("s/<slug:slug>/", views.section, name="section"),
]
