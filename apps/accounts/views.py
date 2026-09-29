"""HTTP qatlami. Biznes logika yo'q — faqat forma → servis → javob."""

import json
import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.crypto import constant_time_compare
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from apps.common.http import safe_next
from apps.core.models import Branch, SchoolSettings

from . import superadmin
from .domain.exceptions import AuthError, OTPError, RateLimited
from .domain.phone import format_phone
from .forms import CodeRequestForm, CodeVerifyForm, PasswordLoginForm, StyledPasswordChangeForm
from .infrastructure import telegram
from .models import OneTimeCode, UserRole
from .services import auth, otp
from .services.telegram_linking import handle_update
from .session import SESSION_ROLE_KEY, start_session

PENDING_KEY = "otp_pending"  # {"phone", "branch_id", "remember", "channel", "next"}
WEBHOOK_MAX_BODY = 64 * 1024
security_log = logging.getLogger("security")


def _safe_next(request, candidate: str | None) -> str:
    """Open redirect himoyasi: faqat o'z saytimizdagi manzillarga qaytaramiz."""
    return safe_next(request, candidate, settings.LOGIN_REDIRECT_URL)


@never_cache
@sensitive_post_parameters("password")
def login_view(request):
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    method = request.POST.get("method") or request.GET.get("method") or settings.LOGIN_DEFAULT_METHOD
    if method not in ("code", "password"):
        method = settings.LOGIN_DEFAULT_METHOD
    is_post = request.method == "POST"
    code_form = CodeRequestForm(request.POST if is_post and method == "code" else None)
    password_form = PasswordLoginForm(request.POST if is_post and method == "password" else None)
    next_url = request.GET.get("next")

    if is_post and method == "code" and code_form.is_valid():
        data = code_form.cleaned_data
        try:
            auth.request_login_code(phone=data["phone"], channel=data["channel"], ip=request.client_ip,
                                    school_name=SchoolSettings.load().short_name)
        except (AuthError, RateLimited) as e:
            code_form.add_error(None, str(e))
        else:
            request.session[PENDING_KEY] = {
                "phone": data["phone"],
                "branch_id": data["branch"].pk if data["branch"] else None,
                "remember": data["remember"],
                "channel": data["channel"],
                "next": _safe_next(request, next_url),
            }
            return redirect("accounts:verify")

    if is_post and method == "password" and password_form.is_valid():
        data = password_form.cleaned_data
        try:
            user = auth.password_login(request=request, phone=data["phone"], password=data["password"],
                                       ip=request.client_ip)
            start_session(request, user, data["branch"], data["remember"])
        except (AuthError, RateLimited) as e:
            password_form.add_error(None, str(e))
        else:
            return redirect(_safe_next(request, next_url))

    return render(request, "accounts/login.html", {
        "method": method,
        "code_form": code_form,
        "password_form": password_form,
        "telegram_ready": telegram.is_configured() or settings.DEBUG,
    })


@never_cache
def verify_view(request):
    pending = request.session.get(PENDING_KEY)
    if not pending:
        return redirect("accounts:login")

    phone = pending["phone"]
    form = CodeVerifyForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            user = auth.verify_login_code(phone=phone, code=form.cleaned_data["code"], ip=request.client_ip)
            branch = Branch.objects.filter(pk=pending.get("branch_id")).first()
            start_session(request, user, branch, pending["remember"])
        except (OTPError, RateLimited) as e:
            form.add_error("code", str(e))
        except AuthError as e:
            request.session.pop(PENDING_KEY, None)
            messages.error(request, str(e))
            return redirect("accounts:login")
        else:
            request.session.pop(PENDING_KEY, None)
            return redirect(pending.get("next") or settings.LOGIN_REDIRECT_URL)

    return render(request, "accounts/verify.html", {
        "form": form,
        "phone_display": format_phone(phone),
        "channel": pending.get("channel", OneTimeCode.Channel.SMS),
        "bot_link": telegram.bot_link(),
        "resend_in": otp.seconds_until_resend(phone, OneTimeCode.Purpose.LOGIN),
        "ttl": settings.OTP_TTL_SECONDS,
    })


@require_POST
def resend_view(request):
    pending = request.session.get(PENDING_KEY)
    if not pending:
        return redirect("accounts:login")
    try:
        auth.request_login_code(phone=pending["phone"], channel=pending.get("channel", OneTimeCode.Channel.SMS),
                                ip=request.client_ip, school_name=SchoolSettings.load().short_name)
    except (AuthError, RateLimited) as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "Yangi kod yuborildi.")
    return redirect("accounts:verify")


@require_POST
def logout_view(request):
    if getattr(request, "impersonator", None):
        # Superadmin xodim qiyofasida: "Chiqish" — tizimdan emas, qiyofadan chiqish.
        superadmin.stop_impersonation(request)
        return redirect("accounts:superadmin")
    logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)


@login_required
@require_POST
def switch_role_view(request, pk):
    role = get_object_or_404(UserRole, pk=pk, user=request.user, is_active=True, branch__is_active=True)
    request.session[SESSION_ROLE_KEY] = role.pk
    messages.success(request, f"{role.get_role_display()} paneliga o'tildi.")
    return redirect("core:home")


def admin_login_redirect(request, extra_context=None):
    """Django admin o'z login formasini ishlatmasin — u rate limitsiz.
    Bizning himoyalangan login sahifamizga yo'naltiramiz."""
    target = _safe_next(request, request.GET.get("next") or reverse("admin:index"))
    return redirect(f"{reverse('accounts:login')}?{urlencode({'method': 'password', 'next': target})}")


@csrf_exempt
@require_POST
def telegram_webhook_view(request, secret):
    """Production: Telegram yangilanishlari shu yerga keladi (setWebhook bilan ulanadi)."""
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    expected = settings.TELEGRAM_WEBHOOK_SECRET
    if not expected or not (constant_time_compare(secret, expected) and constant_time_compare(header, expected)):
        security_log.warning("Telegram webhook: noto'g'ri secret ip=%s", request.client_ip)
        return HttpResponseForbidden()
    if len(request.body) > WEBHOOK_MAX_BODY:
        return HttpResponseBadRequest()
    try:
        update = json.loads(request.body)
    except ValueError:
        return HttpResponseBadRequest()
    if isinstance(update, dict):
        handle_update(update, SchoolSettings.load().short_name)
    return HttpResponse("ok")


@login_required
def profile_view(request):
    user = request.user
    return render(request, "accounts/profile.html", {
        "roles": user.roles.filter(is_active=True).select_related("branch"),
        "telegram": getattr(user, "telegram", None) if hasattr(user, "telegram") else None,
        "teacher": getattr(user, "teacher", None) if hasattr(user, "teacher") else None,
    })


@login_required
@sensitive_post_parameters()
def settings_view(request):
    impersonating = bool(getattr(request, "impersonator", None))
    form = StyledPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST":
        if impersonating:
            # Superadmin xodim qiyofasida parolini o'zgartira olmaydi.
            messages.error(request, "Qiyofa rejimida parolni o'zgartirib bo'lmaydi.")
            return redirect("accounts:settings")
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, form.user)  # joriy sessiya saqlanadi, boshqalari tugaydi
            security_log.info("Parol o'zgartirildi: user=%s", request.user.pk)
            messages.success(request, "Parol o'zgartirildi. Boshqa qurilmalardagi sessiyalar yopildi.")
            return redirect("accounts:settings")
    return render(request, "accounts/settings.html", {
        "form": form, "impersonating": impersonating,
        "telegram": getattr(request.user, "telegram", None) if hasattr(request.user, "telegram") else None,
        "bot_link": telegram.bot_link(),
    })
