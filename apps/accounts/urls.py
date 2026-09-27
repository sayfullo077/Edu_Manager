from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("login/code/", views.verify_view, name="verify"),
    path("login/code/resend/", views.resend_view, name="resend"),
    path("logout/", views.logout_view, name="logout"),
    path("role/<int:pk>/", views.switch_role_view, name="switch_role"),
    path("telegram/webhook/<str:secret>/", views.telegram_webhook_view, name="telegram_webhook"),
]
