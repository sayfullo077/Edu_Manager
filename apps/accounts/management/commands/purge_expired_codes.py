from django.core.management.base import BaseCommand

from apps.accounts.services.otp import purge_expired


class Command(BaseCommand):
    help = "Eski bir martalik kodlarni o'chiradi. Cron orqali kuniga bir marta ishga tushiring."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)

    def handle(self, *args, days, **options):
        self.stdout.write(self.style.SUCCESS(f"O'chirildi: {purge_expired(days)} ta kod"))
