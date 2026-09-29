from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.finance.services.invoices import generate_due_months


class Command(BaseCommand):
    help = ("Imzolangan shartnomalar uchun joriy oygacha yetishmagan to'lov grafigi oylarini yaratadi. "
            "Idempotent — cron orqali kuniga bir marta ishga tushiring (oy boshida yangi oy qo'shiladi).")

    def handle(self, *args, **options):
        created = generate_due_months(timezone.localdate())
        self.stdout.write(self.style.SUCCESS(f"Yaratildi: {created} ta oy"))
