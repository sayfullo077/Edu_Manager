import pytest
from django.core.exceptions import ValidationError
from django.test import RequestFactory, override_settings
from django.urls import reverse

from apps.accounts.infrastructure.sms import LocmemSMSBackend
from apps.accounts.models import Role, User, UserRole
from apps.common import ratelimit
from apps.common.net import client_ip
from apps.core.models import Branch, SchoolSettings

PASSWORD = "Str0ng-pass-123"


@pytest.fixture(autouse=True)
def clear_outbox():
    LocmemSMSBackend.outbox.clear()


@pytest.fixture
def teacher(db):
    branch = Branch.objects.create(name="Test filial")
    user = User.objects.create_user("998901112233", PASSWORD, last_name="Aliyev", first_name="Vali")
    UserRole.objects.create(user=user, role=Role.TEACHER, branch=branch)
    return user


# ---------- Sarlavhalar ----------

def test_security_headers_and_csp_nonce(client, db):
    resp = client.get(reverse("accounts:login"))
    csp = resp["Content-Security-Policy"]
    assert "script-src 'self' 'nonce-" in csp
    assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert resp["X-Frame-Options"] == "DENY"
    assert resp["X-Content-Type-Options"] == "nosniff"
    assert "camera=()" in resp["Permissions-Policy"]
    # Inline skript nonce bilan belgilangan va nonce sarlavhadagisi bilan bir xil
    nonce = csp.split("'nonce-")[1].split("'")[0]
    assert f'<script nonce="{nonce}">' in resp.content.decode()


def test_authenticated_pages_not_cached(client, teacher):
    client.force_login(teacher)
    assert "no-store" in client.get(reverse("core:home"))["Cache-Control"]


def test_robots_and_healthz(client):
    assert "Disallow: /" in client.get("/robots.txt").content.decode()
    assert client.get("/healthz/").json() == {"status": "ok"}


# ---------- Open redirect ----------

@pytest.mark.parametrize("evil", ["https://evil.example/", "//evil.example/", "javascript:alert(1)"])
def test_login_next_open_redirect_blocked(client, teacher, evil):
    resp = client.post(f"{reverse('accounts:login')}?next={evil}",
                       {"method": "password", "phone": "901112233", "password": PASSWORD})
    assert resp.status_code == 302
    assert resp.url == reverse("core:home")


def test_login_next_internal_allowed(client, teacher):
    resp = client.post(f"{reverse('accounts:login')}?next=/s/my-schedule/",
                       {"method": "password", "phone": "901112233", "password": PASSWORD})
    assert resp.url == "/s/my-schedule/"


def test_admin_login_goes_through_our_login(client, db):
    resp = client.get(reverse("admin:login"))
    assert resp.status_code == 302
    assert resp.url.startswith(reverse("accounts:login") + "?method=password")


# ---------- Rate limit: SMS bombing, brute force ----------

def test_sms_bombing_limited_per_ip(client, db):
    """Bitta IP'dan turli raqamlarga cheksiz SMS yuborib, pulimizni sarflab bo'lmaydi."""
    limit = ratelimit.get_limit("otp_request_ip").limit
    for i in range(limit + 3):
        User.objects.create_user(f"99890000{i:04d}", last_name="X", first_name="Y")
        client.post(reverse("accounts:login"), {"method": "code", "phone": f"90000{i:04d}"})
    assert len(LocmemSMSBackend.outbox) == limit


def test_sms_limited_per_phone_across_ips(client, teacher, settings):
    settings.OTP_RESEND_SECONDS = 0
    limit = ratelimit.get_limit("otp_request_phone").limit
    for i in range(limit + 2):
        client.post(reverse("accounts:login"), {"method": "code", "phone": "901112233"},
                    REMOTE_ADDR=f"10.0.0.{i}")
    assert len(LocmemSMSBackend.outbox) == limit


def test_password_bruteforce_blocked_per_account_across_ips(client, teacher):
    """Credential stuffing: turli IP'lardan bitta akkauntga hujum."""
    limit = ratelimit.get_limit("password_phone").limit
    for i in range(limit):
        client.post(reverse("accounts:login"), {"method": "password", "phone": "901112233", "password": "wrong"},
                    REMOTE_ADDR=f"10.1.0.{i}")
    # Limitdan keyin hatto to'g'ri parol ham vaqtincha qabul qilinmaydi
    resp = client.post(reverse("accounts:login"), {"method": "password", "phone": "901112233",
                                                   "password": PASSWORD}, REMOTE_ADDR="10.9.9.9")
    assert resp.status_code == 200
    assert "Juda ko&#x27;p urinish" in resp.content.decode()


def test_successful_login_not_counted(client, teacher):
    for _ in range(ratelimit.get_limit("password_phone").limit + 2):
        client.post(reverse("accounts:login"), {"method": "password", "phone": "901112233", "password": PASSWORD})
        client.logout()
    assert ratelimit.peek("password_phone", "998901112233").allowed


@override_settings(RATE_LIMITS={**__import__("django.conf").conf.settings.RATE_LIMITS, "global_ip": (3, 60)})
def test_global_rate_limit_returns_429(client, db):
    codes = [client.get(reverse("accounts:login")).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429
    assert client.get("/healthz/").status_code == 200  # healthcheck limitga tushmaydi


# ---------- IP aniqlash ----------

@pytest.mark.parametrize("hops, xff, expected", [
    (0, "1.1.1.1", "9.9.9.9"),                 # proksi yo'q: sarlavhaga ishonilmaydi
    (1, "6.6.6.6, 1.1.1.1", "1.1.1.1"),        # nginx: oxirgi qo'shilgan manzil
    (2, "6.6.6.6, 2.2.2.2, 1.1.1.1", "2.2.2.2"),  # Cloudflare + nginx
    (1, "not-an-ip", "9.9.9.9"),               # buzuq sarlavha
])
def test_client_ip_respects_trusted_proxies(settings, hops, xff, expected):
    settings.TRUSTED_PROXY_COUNT = hops
    request = RequestFactory().get("/", REMOTE_ADDR="9.9.9.9", HTTP_X_FORWARDED_FOR=xff)
    assert client_ip(request) == expected


# ---------- Validatsiya ----------

def test_brand_color_rejects_css_injection(db):
    school = SchoolSettings.load()
    school.brand_color = "red;}body{display:none"
    with pytest.raises(ValidationError):
        school.save()


def test_school_settings_cached(db, django_assert_num_queries):
    SchoolSettings.load()
    with django_assert_num_queries(0):
        SchoolSettings.load()


def test_webhook_rejects_oversized_body(client, db):
    url = reverse("accounts:telegram_webhook", args=["test-secret"])
    resp = client.post(url, "x" * (70 * 1024), content_type="application/json",
                       headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
    assert resp.status_code == 400
