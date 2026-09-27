import time
import traceback
import urllib.error

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.infrastructure.telegram import BotAPITelegramBackend
from apps.accounts.services.telegram_linking import handle_update
from apps.core.models import SchoolSettings

POLL_TIMEOUT = 30


class Command(BaseCommand):
    help = "Telegram botni long-polling rejimida ishga tushiradi (development va kichik serverlar uchun)."

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError(".env faylida TELEGRAM_BOT_TOKEN ni belgilang (@BotFather'dan olinadi).")

        api = BotAPITelegramBackend()
        me = api.call("getMe", {})["result"]
        # Webhook o'rnatilgan bo'lsa getUpdates ishlamaydi.
        api.call("deleteWebhook", {"drop_pending_updates": False})
        self.stdout.write(self.style.SUCCESS(f"@{me['username']} ishga tushdi. To'xtatish: Ctrl+C"))

        offset = None
        while True:
            try:
                payload = {"timeout": POLL_TIMEOUT, "allowed_updates": ["message"]}
                if offset is not None:
                    payload["offset"] = offset
                updates = api.call("getUpdates", payload, timeout=POLL_TIMEOUT + 10)["result"]
            except (urllib.error.URLError, TimeoutError) as e:
                self.stderr.write(f"Tarmoq xatosi: {e}. 5 soniyadan keyin qayta urinaman.")
                time.sleep(5)
                continue

            school = SchoolSettings.load().short_name
            for update in updates:
                offset = update["update_id"] + 1
                try:
                    handle_update(update, school)
                except Exception:  # bitta buzuq xabar botni to'xtatmasin
                    self.stderr.write(
                        f"Update {update['update_id']} ni qayta ishlashda xato:\n{traceback.format_exc()}")
