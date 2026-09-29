from django.urls import path

from . import superadmin_views, views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("login/code/", views.verify_view, name="verify"),
    path("login/code/resend/", views.resend_view, name="resend"),
    path("logout/", views.logout_view, name="logout"),
    path("role/<int:pk>/", views.switch_role_view, name="switch_role"),
    path("profile/", views.profile_view, name="profile"),
    path("settings/", views.settings_view, name="settings"),
    path("telegram/webhook/<str:secret>/", views.telegram_webhook_view, name="telegram_webhook"),
    path("superadmin/", superadmin_views.panel, name="superadmin"),
    path("superadmin/view-as/", superadmin_views.view_as_role, name="superadmin_view_as"),
    path("superadmin/view-as/exit/", superadmin_views.exit_role_view, name="superadmin_exit_role"),
    path("superadmin/impersonate/<int:user_pk>/", superadmin_views.impersonate, name="superadmin_impersonate"),
    path("superadmin/impersonate/stop/", superadmin_views.stop_impersonation, name="superadmin_stop"),
]
