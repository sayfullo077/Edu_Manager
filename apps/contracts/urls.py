from django.urls import path

from . import views

app_name = "contracts"

urlpatterns = [
    path("contracts/", views.contract_list, name="contract_list"),
    path("contracts/export/", views.contract_export, name="contract_export"),
    path("students/<int:student_pk>/contract/new/", views.contract_create, name="contract_create"),
    path("contracts/<int:pk>/", views.contract_detail, name="contract_detail"),
    path("contracts/<int:pk>/edit/", views.contract_update, name="contract_update"),
    path("contracts/<int:pk>/send-code/", views.contract_send_code, name="contract_send_code"),
    path("contracts/<int:pk>/confirm/", views.contract_confirm, name="contract_confirm"),
    path("contracts/<int:pk>/cancel/", views.contract_cancel, name="contract_cancel"),
    path("contracts/<int:pk>/scan/", views.contract_scan, name="contract_scan"),
    path("contracts/<int:pk>/scan/upload/", views.contract_upload_scan, name="contract_upload_scan"),
    path("contracts/<int:pk>/print/", views.contract_print, name="contract_print"),
]
