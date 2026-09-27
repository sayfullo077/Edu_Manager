from .base import *  # noqa: F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
SMS_BACKEND = "apps.accounts.infrastructure.sms.LocmemSMSBackend"
TELEGRAM_BACKEND = "apps.accounts.infrastructure.telegram.LocmemTelegramBackend"
TELEGRAM_BOT_USERNAME = "test_school_bot"
TELEGRAM_WEBHOOK_SECRET = "test-secret"
