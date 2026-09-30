from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.dorm.services import billing as dorm_billing
from apps.finance.services.invoices import generate_due_months


class Command(BaseCommand):
    help = ("Imzolangan shartnomalar uchun joriy oygacha yetishmagan to'lov grafigi oylarini yaratadi. "
            "Idempotent — cron orqali kuniga bir marta ishga tushiring (oy boshida yangi oy qo'shiladi).")

    def handle(self, *args, **options):
        today = timezone.localdate()
        tuition, dorm = generate_due_months(today), dorm_billing.generate_due_months(today)
        self.stdout.write(self.style.SUCCESS(f"Yaratildi: o'qish {tuition} ta, yotoqxona {dorm} ta oy"))
