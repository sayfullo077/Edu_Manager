from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import (
    ALLOWED_HOSTS,
    DATABASES,
    FIELD_ENCRYPTION_KEYS,
    FIELD_INDEX_KEY,
    INSECURE_DEV_KEY,
    REDIS_URL,
    SECRET_KEY,
    STORAGES,
    env,
)

# ---------- Majburiy tekshiruvlar: noto'g'ri sozlangan server ishga tushmasin ----------
if SECRET_KEY == INSECURE_DEV_KEY or len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("Production uchun kamida 50 belgili SECRET_KEY belgilang.")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS ni belgilang (masalan: maktab.uz).")
if not FIELD_ENCRYPTION_KEYS or not FIELD_INDEX_KEY:
    raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS va FIELD_INDEX_KEY majburiy (shaxsiy ma'lumotlarni shifrlash).")
if not REDIS_URL:
    raise ImproperlyConfigured("REDIS_URL majburiy: rate limit barcha workerlar orasida umumiy bo'lishi kerak.")

DEBUG = False

# ---------- HTTPS ----------
# HTTPS=false — FAQAT domensiz, IP orqali qisqa MVP sinovi uchun (parollar shifrsiz uzatiladi!).
# Haqiqiy foydalanishda domen + Let's Encrypt bilan HTTPS=true (docs/DEPLOY.md).
HTTPS = env.bool("HTTPS", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
if HTTPS:
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_NAME = "__Host-edu_sid"   # __Host- prefiksi: faqat HTTPS, subdomen o'g'irlay olmaydi
    CSRF_COOKIE_NAME = "__Host-csrftoken"
else:
    import warnings

    warnings.warn("HTTPS=false: sayt shifrsiz HTTP orqali ishlayapti — faqat qisqa sinov uchun!", stacklevel=1)
    SECURE_SSL_REDIRECT = False
    SECURE_HSTS_SECONDS = 0
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

# ---------- Unumdorlik ----------
# psycopg3 connection pool: har so'rovda yangi ulanish ochilmaydi.
DATABASES["default"]["CONN_MAX_AGE"] = 0  # pool bilan birga 0 bo'lishi shart
DATABASES["default"]["OPTIONS"]["pool"] = {
    "min_size": env.int("DB_POOL_MIN", default=2),
    "max_size": env.int("DB_POOL_MAX", default=10),
    "timeout": 10,
}
# Static fayllar: siqilgan (gzip/brotli) + hash'li nomlar → brauzer 1 yil keshlaydi.
STORAGES = {**STORAGES, "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}
