"""Moliya: to'lov grafiklari (Invoice), hisoblar, kassa sessiyasi, to'lovlar, tranzaksiyalar, xarajatlar, byudjet.

Asosiy qoidalar:
- Pul faqat Decimal. Summalar so'mda (tiyinsiz), lekin DecimalField(…, 2) — kelajakdagi o'zgarishlarga zaxira.
- Moliyaviy yozuvlar O'CHIRILMAYDI. Xato to'lov → storno (teskari tranzaksiya), yozuv tarixda qoladi.
- Har bir pul harakati `Transaction` jurnalida — hisob qoldiqlari faqat shu jurnaldan hisoblanadi.
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.common.models import CodeSequence
from apps.core.models import Branch, TimeStampedModel

MONEY = {"max_digits": 14, "decimal_places": 2}
POSITIVE = [MinValueValidator(Decimal("0.01"))]


class Invoice(TimeStampedModel):
    """To'lov grafigi qatori: bitta o'quvchining bitta oy uchun to'lashi kerak bo'lgan summasi."""

    class Category(models.TextChoices):
        TUITION = "tuition", "O'qish to'lovi"
        DORM = "dorm", "Yotoqxona to'lovi"

    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        PARTIAL = "partial", "Qisman"
        PAID = "paid", "To'langan"
        CANCELLED = "cancelled", "Bekor qilingan"

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="invoices")
    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="invoices",
                                verbose_name="o'quvchi")
    contract = models.ForeignKey("contracts.Contract", on_delete=models.PROTECT, null=True, blank=True,
                                 related_name="invoices", verbose_name="shartnoma")
    category = models.CharField("turi", max_length=10, choices=Category.choices, default=Category.TUITION)
    month = models.DateField("oy", help_text="Oyning 1-sanasi")
    full_amount = models.DecimalField("to'liq tarif", **MONEY, help_text="Chegirmasiz, to'liq oy uchun")
    discount = models.DecimalField("chegirma", **MONEY, default=Decimal("0"))
    waived = models.DecimalField("kechilgan", **MONEY, default=Decimal("0"),
                                 help_text="Oy o'rtasida kelgani uchun hisoblanmagan qism va boshqa kechishlar")
    amount = models.DecimalField("to'lanishi kerak", **MONEY)
    paid = models.DecimalField("to'langan", **MONEY, default=Decimal("0"))
    due_date = models.DateField("to'lov muddati")
    status = models.CharField("holati", max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)

    class Meta:
        verbose_name = "to'lov grafigi"
        verbose_name_plural = "to'lov grafiklari"
        ordering = ["month", "student__last_name"]
        constraints = [
            models.UniqueConstraint(fields=["student", "category", "month"],
                                    condition=~models.Q(status="cancelled"), name="one_invoice_per_month"),
            models.CheckConstraint(condition=models.Q(paid__gte=0) & models.Q(paid__lte=models.F("amount")),
                                   name="invoice_paid_within_amount"),
        ]
        indexes = [models.Index(fields=["branch", "month", "status"])]

    def __str__(self):
        return f"{self.student} · {self.month:%Y-%m}"

    @property
    def remaining(self) -> Decimal:
        return self.amount - self.paid

    @property
    def gross(self) -> Decimal:
        """Oylik (chegirmadan keyin, kechilgandan oldin) — "To'lov grafiklari"dagi "Jami"."""
        return self.amount + self.waived

    def refresh_status(self) -> None:
        if self.status == self.Status.CANCELLED:
            return
        if self.paid >= self.amount:
            self.status = self.Status.PAID
        elif self.paid > 0:
            self.status = self.Status.PARTIAL
        else:
            self.status = self.Status.PENDING


class Account(models.Model):
    """Pul turadigan joy: naqd kassa, bank hisobi, terminal."""

    class Kind(models.TextChoices):
        CASH = "cash", "Naqd kassa"
        BANK = "bank", "Bank hisobi"
        TERMINAL = "terminal", "Terminal (karta)"

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="accounts")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    name = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "hisob"
        verbose_name_plural = "hisoblar"
        constraints = [models.UniqueConstraint(fields=["branch", "kind"], name="one_account_kind_per_branch")]

    def __str__(self):
        return self.name


class CashSession(models.Model):
    """Kassa smenasi: kun boshida ochiladi, oxirida sanab yopiladi. Naqd to'lov faqat ochiq sessiyada."""

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="cash_sessions")
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    opened_at = models.DateTimeField(auto_now_add=True)
    opening_balance = models.DecimalField("boshlang'ich qoldiq", **MONEY)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="+")
    closed_at = models.DateTimeField(null=True, blank=True)
    expected_cash = models.DecimalField("kutilgan naqd", **MONEY, null=True, blank=True)
    counted_cash = models.DecimalField("sanalgan naqd", **MONEY, null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "kassa sessiyasi"
        verbose_name_plural = "kassa sessiyalari"
        ordering = ["-opened_at"]
        constraints = [models.UniqueConstraint(fields=["branch"], condition=models.Q(closed_at__isnull=True),
                                               name="one_open_cash_session_per_branch")]

    def __str__(self):
        return f"Kassa {self.opened_at:%d.%m.%Y}"

    @property
    def difference(self):
        if self.counted_cash is None or self.expected_cash is None:
            return None
        return self.counted_cash - self.expected_cash


class Payment(TimeStampedModel):
    class Method(models.TextChoices):
        CASH = "cash", "Naqd"
        CARD = "card", "Karta (terminal)"
        TRANSFER = "transfer", "Bank o'tkazmasi"

    class CardNetwork(models.TextChoices):
        HUMO = "humo", "Humo"
        MASTERCARD = "mastercard", "Mastercard"
        UZCARD = "uzcard", "Uzcard"
        VISA = "visa", "Visa"
        OTHER = "other", "Boshqa"

    class Status(models.TextChoices):
        OK = "ok", "Qabul qilingan"
        REVERSED = "reversed", "Storno qilingan"

    number = models.CharField("kvitansiya", max_length=20, unique=True, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="payments")
    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="payments",
                                verbose_name="o'quvchi")
    category = models.CharField("turi", max_length=10, choices=Invoice.Category.choices,
                                default=Invoice.Category.TUITION)
    amount = models.DecimalField("summa", **MONEY, validators=POSITIVE)
    method = models.CharField("to'lov usuli", max_length=10, choices=Method.choices)
    card_network = models.CharField("karta turi", max_length=10, choices=CardNetwork.choices, blank=True)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="payments")
    cash_session = models.ForeignKey(CashSession, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name="payments")
    paid_at = models.DateTimeField("to'langan vaqt")
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+",
                                    verbose_name="qabul qilgan")
    payer_name = models.CharField("to'lovchi", max_length=120, blank=True)
    status = models.CharField("holati", max_length=10, choices=Status.choices, default=Status.OK, db_index=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="+")
    reverse_reason = models.CharField(max_length=255, blank=True)
    note = models.CharField("izoh", max_length=255, blank=True)

    class Meta:
        verbose_name = "to'lov"
        verbose_name_plural = "to'lovlar"
        ordering = ["-paid_at"]
        indexes = [models.Index(fields=["branch", "paid_at"])]

    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = CodeSequence.next_code("PAY", self.paid_at.year, width=5)
        super().save(*args, **kwargs)


class PaymentAllocation(models.Model):
    """To'lovning qaysi oy(lar)ga taqsimlangani. Bitta to'lov bir necha oyni yopishi mumkin."""

    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="allocations")
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="allocations")
    amount = models.DecimalField(**MONEY, validators=POSITIVE)

    class Meta:
        verbose_name = "to'lov taqsimoti"
        verbose_name_plural = "to'lov taqsimotlari"

    def __str__(self):
        return f"{self.payment} → {self.invoice}: {self.amount}"


class ExpenseCategory(models.Model):
    class Kind(models.TextChoices):
        FIXED = "fixed", "Doimiy (oy sayin bir xil limit)"
        NORMATIVE = "normative", "Normativ (o'zgaruvchan limit)"

    name = models.CharField(max_length=80, unique=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    icon = models.CharField(max_length=20, default="receipt")
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "xarajat kategoriyasi"
        verbose_name_plural = "xarajat kategoriyalari"
        ordering = ["kind", "order", "name"]

    def __str__(self):
        return self.name


class BudgetLimit(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="budget_limits")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="limits")
    month = models.DateField(help_text="Oyning 1-sanasi")
    limit = models.DecimalField("limit", **MONEY, validators=[MinValueValidator(0)])

    class Meta:
        verbose_name = "byudjet limiti"
        verbose_name_plural = "byudjet limitlari"
        constraints = [models.UniqueConstraint(fields=["branch", "category", "month"], name="one_limit_per_month")]

    def __str__(self):
        return f"{self.category} · {self.month:%Y-%m}: {self.limit}"


class Expense(TimeStampedModel):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="expenses")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="expenses",
                                 verbose_name="kategoriya")
    amount = models.DecimalField("summa", **MONEY, validators=POSITIVE)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="expenses", verbose_name="hisob")
    cash_session = models.ForeignKey(CashSession, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name="expenses")
    spent_at = models.DateField("sana")
    description = models.CharField("izoh", max_length=255)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    is_reversed = models.BooleanField(default=False)

    class Meta:
        verbose_name = "xarajat"
        verbose_name_plural = "xarajatlar"
        ordering = ["-spent_at", "-created_at"]
        indexes = [models.Index(fields=["branch", "spent_at"])]

    def __str__(self):
        return f"{self.category}: {self.amount}"


class Transaction(models.Model):
    """Pul harakatlari jurnali (append-only). Hisob qoldig'i = kirimlar − chiqimlar."""

    class Direction(models.TextChoices):
        IN = "in", "Kirim"
        OUT = "out", "Chiqim"

    class Kind(models.TextChoices):
        PAYMENT = "payment", "O'quvchi to'lovi"
        EXPENSE = "expense", "Xarajat"
        STORNO = "storno", "Storno"
        TRANSFER = "transfer", "Ichki o'tkazma"
        ADJUSTMENT = "adjustment", "Kassa tafovuti"
        REFUND = "refund", "Qaytarilgan to'lov"

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="transactions")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="transactions")
    direction = models.CharField(max_length=3, choices=Direction.choices)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    amount = models.DecimalField(**MONEY, validators=POSITIVE)
    commission = models.DecimalField(**MONEY, default=Decimal("0"), help_text="Bank/terminal komissiyasi")
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, null=True, blank=True, related_name="transactions")
    expense = models.ForeignKey(Expense, on_delete=models.PROTECT, null=True, blank=True, related_name="transactions")
    withdrawal = models.ForeignKey("Withdrawal", on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="transactions")
    occurred_at = models.DateTimeField(db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "tranzaksiya"
        verbose_name_plural = "tranzaksiyalar"
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["branch", "occurred_at"]), models.Index(fields=["account", "direction"])]

    def __str__(self):
        return f"{self.get_direction_display()} {self.amount}"

    @property
    def net(self) -> Decimal:
        return self.amount - self.commission

    @property
    def category_label(self) -> str:
        """Jadval uchun kategoriya: to'lovlar o'qish / yotoqxona bo'yicha ajratiladi."""
        if self.kind == self.Kind.PAYMENT and self.payment_id and self.payment.category == Invoice.Category.DORM:
            return "Yotoqxona to'lovi"
        return self.get_kind_display()

    @property
    def status_key(self) -> str:
        """"ok" | "cancelled" (keyin storno qilingan to'lov) | "storno" (teskari yozuvning o'zi)."""
        if self.kind == self.Kind.STORNO:
            return "storno"
        if self.kind == self.Kind.PAYMENT and self.payment_id and self.payment.status == Payment.Status.REVERSED:
            return "cancelled"
        return "ok"


class Withdrawal(models.Model):
    """O'quvchining o'qishdan chiqishi — yakuniy hisob-kitob (append-only, o'chirilmaydi).

    Chiqish sanasigacha o'qigan kunlar hisoblanadi, kelajak oylar bekor qilinadi, ortiqcha to'lov qaytariladi
    (`Transaction` REFUND), kam to'langan bo'lsa qarz grafikda qoladi. Har bir oy o'zgarishi `WithdrawalLine` da.
    """

    class Reason(models.TextChoices):
        TRANSFER = "transfer", "Boshqa maktabga ko'chdi"
        RELOCATION = "relocation", "Yashash joyini o'zgartirdi"
        DROPOUT = "dropout", "O'qishni tashladi"
        FINANCIAL = "financial", "To'lov qila olmaydi"
        EXPELLED = "expelled", "Maktab tomonidan chetlatildi"
        OTHER = "other", "Boshqa"

    class RefundMethod(models.TextChoices):
        CASH = "cash", "Naqd (kassadan)"
        TRANSFER = "transfer", "Bank o'tkazmasi"

    number = models.CharField("raqami", max_length=20, unique=True, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="withdrawals")
    student = models.OneToOneField("people.Student", on_delete=models.PROTECT, related_name="withdrawal",
                                   verbose_name="o'quvchi")
    left_on = models.DateField("o'qishdan chiqqan sana")
    dorm_left_on = models.DateField("yotoqxonadan chiqqan sana", null=True, blank=True)
    reason = models.CharField("sababi", max_length=12, choices=Reason.choices)
    note = models.CharField("izoh", max_length=255, blank=True)
    charged = models.DecimalField("hisoblangan (jami)", **MONEY)
    paid = models.DecimalField("to'langan (jami)", **MONEY)
    refund = models.DecimalField("qaytarilgan", **MONEY, default=Decimal("0"))
    debt = models.DecimalField("qolgan qarz", **MONEY, default=Decimal("0"))
    refund_method = models.CharField("qaytarish usuli", max_length=10, choices=RefundMethod.choices, blank=True)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    cash_session = models.ForeignKey(CashSession, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+",
                                   verbose_name="rasmiylashtirgan")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "o'qishdan chiqish"
        verbose_name_plural = "o'qishdan chiqishlar"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.number} · {self.student}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = CodeSequence.next_code("EXT", self.left_on.year)
        super().save(*args, **kwargs)


class WithdrawalLine(models.Model):
    """Chiqishda bitta oy grafigining o'zgarishi (audit): eski/yangi summa va to'langan."""

    withdrawal = models.ForeignKey(Withdrawal, on_delete=models.PROTECT, related_name="lines")
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="+")
    old_amount = models.DecimalField(**MONEY)
    new_amount = models.DecimalField(**MONEY)
    old_paid = models.DecimalField(**MONEY)
    new_paid = models.DecimalField(**MONEY)

    class Meta:
        verbose_name = "chiqish qatori"
        verbose_name_plural = "chiqish qatorlari"

    def __str__(self):
        return f"{self.invoice}: {self.old_amount} → {self.new_amount}"
