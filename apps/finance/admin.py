from django.contrib import admin

from .models import (
    Account,
    BudgetLimit,
    CashSession,
    Expense,
    ExpenseCategory,
    Invoice,
    Payment,
    PaymentAllocation,
    Transaction,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    """Moliyaviy yozuvlar faqat servislar orqali o'zgaradi — admin'da faqat ko'rish."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Invoice)
class InvoiceAdmin(ReadOnlyAdmin):
    list_display = ["student", "month", "amount", "paid", "status", "due_date"]
    list_filter = ["status", "category", "month"]
    search_fields = ["student__last_name", "student__first_name", "student__code"]
    list_select_related = ["student"]


class AllocationInline(admin.TabularInline):
    model = PaymentAllocation
    extra = 0
    can_delete = False
    readonly_fields = ["invoice", "amount"]


@admin.register(Payment)
class PaymentAdmin(ReadOnlyAdmin):
    list_display = ["number", "student", "amount", "method", "paid_at", "status", "received_by"]
    list_filter = ["status", "method", "branch"]
    search_fields = ["number", "student__last_name", "student__code"]
    list_select_related = ["student", "received_by"]
    inlines = [AllocationInline]


@admin.register(Transaction)
class TransactionAdmin(ReadOnlyAdmin):
    list_display = ["occurred_at", "direction", "kind", "amount", "commission", "account", "description"]
    list_filter = ["direction", "kind", "account"]
    date_hierarchy = "occurred_at"


@admin.register(CashSession)
class CashSessionAdmin(ReadOnlyAdmin):
    list_display = ["opened_at", "opened_by", "opening_balance", "closed_at", "expected_cash", "counted_cash"]


@admin.register(Expense)
class ExpenseAdmin(ReadOnlyAdmin):
    list_display = ["spent_at", "category", "amount", "account", "description", "created_by"]
    list_filter = ["category", "account"]


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "branch", "is_active"]


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "icon", "order", "is_active"]
    list_editable = ["order", "is_active"]


@admin.register(BudgetLimit)
class BudgetLimitAdmin(admin.ModelAdmin):
    list_display = ["category", "month", "limit", "branch"]
    list_filter = ["month", "branch"]
