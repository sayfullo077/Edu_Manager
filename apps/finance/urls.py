from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("students/<int:student_pk>/pay/", views.payment_create, name="payment_create"),
    path("students/<int:student_pk>/schedule/", views.schedule_create, name="schedule_create"),
    path("students/<int:student_pk>/withdraw/", views.student_withdraw, name="student_withdraw"),
    path("students/<int:student_pk>/invoices.xlsx", views.student_invoices_export, name="student_invoices_export"),
    path("payments/", views.payment_list, name="payment_list"),
    path("transactions/", views.transaction_list, name="transaction_list"),
    path("bank/", views.bank_account, name="bank_account"),
    path("invoices/", views.invoice_list, name="invoice_list"),
    path("debtors/", views.debtor_list, name="debtor_list"),
    path("debtors/export/", views.debtor_export, name="debtor_export"),
    path("debtors/<int:student_pk>/<str:kind>/", views.debtor_panel, name="debtor_panel"),
    path("invoices/export/", views.invoice_export, name="invoice_export"),
    path("transactions/export/", views.transaction_export, name="transaction_export"),
    path("payments/export/", views.payment_export, name="payment_export"),
    path("payments/<int:pk>/receipt/", views.payment_receipt, name="payment_receipt"),
    path("payments/<int:pk>/reverse/", views.payment_reverse, name="payment_reverse"),
    path("cashbox/", views.cashbox, name="cashbox"),
    path("cashbox/open/", views.cashbox_open, name="cashbox_open"),
    path("expenses/new/", views.expense_create, name="expense_create"),
    path("budget/", views.budget_edit, name="budget_edit"),
]
