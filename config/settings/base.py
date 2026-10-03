from pathlib import Path

import environ
from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

INSECURE_DEV_KEY = "django-insecure-dev-only-change-me"
SECRET_KEY = env("SECRET_KEY", default=INSECURE_DEV_KEY)
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.postgres",
    "apps.common",
    "apps.core",
    "apps.accounts",
    "apps.academics",
    "apps.people",
    "apps.contracts",
    "apps.finance",
    "apps.dorm",
    "apps.payroll",
    "apps.director",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.common.middleware.ClientIPMiddleware",
    "apps.common.middleware.GlobalRateLimitMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.ImpersonationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "apps.common.middleware.SecurityHeadersMiddleware",
    "apps.accounts.middleware.ActiveRoleMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.csp",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.school",
                "apps.accounts.context_processors.roles",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------- Ma'lumotlar bazasi ----------
DATABASES = {"default": env.db("DATABASE_URL", default="postgres://localhost:5432/edu_manager")}
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"].setdefault("OPTIONS", {})
# Sekin so'rov butun workerni band qilib qo'ymasin (DoS'ga qarshi ham).
DATABASES["default"]["OPTIONS"]["options"] = f"-c statement_timeout={env.int('DB_STATEMENT_TIMEOUT_MS', 15000)}"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------- Kesh (rate limit, sessiya, maktab sozlamalari) ----------
# Production'da Redis majburiy: rate limit barcha worker/serverlar orasida umumiy bo'lishi kerak.
REDIS_URL = env("REDIS_URL", default="")
if REDIS_URL:
    CACHES = {"default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "edu",
        "TIMEOUT": 300,
    }}
    SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "edu"}}

# ---------- Autentifikatsiya ----------
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "accounts:login"
# Rolning bosh sahifasi (bo'lmasa umumiy bosh sahifa ko'rsatiladi).
ROLE_DASHBOARDS = {"reception": "apps.finance.views.dashboard", "head_teacher": "apps.people.views.head_dashboard",
                   "teacher": "apps.academics.views.teacher_dashboard", "director": "apps.director.views.dashboard"}
# SMS provayder ulanguncha asosiy usul — parol. SMS ulangach "code" ga o'zgartirish mumkin.
LOGIN_DEFAULT_METHOD = env("LOGIN_DEFAULT_METHOD", default="password")

# Argon2 — parol xeshlash uchun hozirgi eng yaxshi tavsiya (GPU brute-force'ga chidamli).
# Eski PBKDF2 xeshlar birinchi kirishda avtomatik Argon2'ga o'tkaziladi.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------- Sessiya va cookie ----------
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_NAME = "edu_sid"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_FAILURE_VIEW = "apps.common.views.csrf_failure"

# ---------- Xavfsizlik sarlavhalari ----------
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# Content Security Policy: faqat o'z serverimiz + Google Fonts. Inline skript/stil faqat nonce bilan.
# XSS topilgan taqdirda ham begona skript ishga tushmaydi.
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.NONCE],
    "style-src": [CSP.SELF, CSP.NONCE, "https://fonts.googleapis.com"],
    "font-src": [CSP.SELF, "https://fonts.gstatic.com"],
    "img-src": [CSP.SELF, "data:"],
    "connect-src": [CSP.SELF],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
}

# ---------- Yuklanadigan ma'lumot hajmi (resurs tugatish hujumlariga qarshi) ----------
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 500
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

# ---------- Shaxsiy ma'lumotlarni shifrlash (passport, JSHSHIR) ----------
# Fernet kalitlari (vergul bilan, birinchisi — joriy). Yaratish:
#   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Dev'da bo'sh bo'lsa SECRET_KEY'dan hosil qilinadi. KALITNI YO'QOTSANGIZ, MA'LUMOT QAYTMAYDI.
FIELD_ENCRYPTION_KEYS = env.list("FIELD_ENCRYPTION_KEYS", default=[])
FIELD_INDEX_KEY = env("FIELD_INDEX_KEY", default="")

# ---------- Proksi va IP ----------
# Oldimizda nechta ishonchli proksi bor: 0 — to'g'ridan-to'g'ri, 1 — nginx, 2 — Cloudflare + nginx.
TRUSTED_PROXY_COUNT = env.int("TRUSTED_PROXY_COUNT", default=0)

# ---------- Rate limitlar: nom → (limit, oyna soniyada) ----------
GLOBAL_RATE_LIMIT_ENABLED = env.bool("GLOBAL_RATE_LIMIT_ENABLED", default=True)
RATE_LIMITS = {
    "global_ip": (300, 60),            # har bir IP: daqiqasiga 300 so'rov
    "otp_request_ip": (10, 60 * 10),   # SMS bombing: bitta IP 10 daqiqada 10 ta kod
    "otp_request_phone": (5, 60 * 60), # bitta raqamga soatiga 5 ta kod (SMS xarajati)
    "otp_verify_ip": (30, 60 * 10),    # kod terish: bitta IP 10 daqiqada 30 urinish
    "password_ip": (20, 60 * 15),      # parol: bitta IP 15 daqiqada 20 xato
    "password_phone": (10, 60 * 15),   # bitta akkauntga (turli IP'lardan) 15 daqiqada 10 xato
    "contract_code_ip": (20, 60 * 60),     # shartnoma SMS'i: bitta xodim IP'sidan soatiga 20 ta
    "contract_code_phone": (3, 60 * 60),   # bitta ota-onaga soatiga 3 ta shartnoma SMS
}

# ---------- Admin ----------
# Standart /admin/ manzili botlar tomonidan doim skanerlanadi — production'da o'zgartiring.
ADMIN_URL = env("ADMIN_URL", default="admin/")

# ---------- Til va vaqt ----------
LANGUAGE_CODE = "uz"
LANGUAGES = [("uz", "O'zbekcha"), ("ru", "Русский")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

# ---------- Static va media ----------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
# Shaxsiy hujjatlar (shartnoma skanerlari): veb-server to'g'ridan-to'g'ri bermaydi.
PRIVATE_MEDIA_ROOT = env.path("PRIVATE_MEDIA_ROOT", default=BASE_DIR / "private_media")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# ---------- Bir martalik kod (OTP) ----------
OTP_LENGTH = 6
OTP_TTL_SECONDS = 180
OTP_RESEND_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
SMS_BACKEND = env("SMS_BACKEND", default="apps.accounts.infrastructure.sms.ConsoleSMSBackend")

# ---------- Moliya ----------
INVOICE_DUE_DAY = 10                 # har oyning shu sanasigacha to'lanadi
INVOICE_PRORATION_GRACE_DAYS = 5     # oyning 1–5-kunlari kelgan o'quvchi to'liq oy to'laydi
INVOICE_ROUNDING = 1000              # oy o'rtasidagi summa mingga (pastga) yaxlitlanadi: 933 333 → 933 000
PAYMENT_BACKDATE_DAYS = 31            # karta/o'tkazma to'lovini necha kun oldingi sana bilan kiritish mumkin
# "Xarajatlar va byudjet" sahifasi hozircha yopiq (ma'lumot faqat rahbariyat uchun) — Reception'ga ochilganda True
BUDGET_PAGE_ENABLED = False
TERMINAL_COMMISSION_PERCENT = env.float("TERMINAL_COMMISSION_PERCENT", default=0.2)

# ---------- Telegram bot (@BotFather). Token bo'lmasa xabarlar terminalga chiqadi ----------
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", default="")
TELEGRAM_BOT_USERNAME = env("TELEGRAM_BOT_USERNAME", default="")  # @ belgisisiz
TELEGRAM_WEBHOOK_SECRET = env("TELEGRAM_WEBHOOK_SECRET", default="")
TELEGRAM_BACKEND = env(
    "TELEGRAM_BACKEND",
    default="apps.accounts.infrastructure.telegram.BotAPITelegramBackend" if TELEGRAM_BOT_TOKEN
    else "apps.accounts.infrastructure.telegram.ConsoleTelegramBackend",
)

# ---------- Loglash ----------
# "security" logger: xato parollar, rate limit, begona Telegram kontaktlari. Prod'da alohida monitoring.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"level": "WARNING"},
        "django.security": {"level": "WARNING"},
        "security": {"level": "INFO"},
    },
}
