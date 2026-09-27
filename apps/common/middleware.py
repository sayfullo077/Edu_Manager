import logging

from django.conf import settings
from django.http import HttpResponse

from . import ratelimit
from .net import client_ip

security_log = logging.getLogger("security")


class ClientIPMiddleware:
    """request.client_ip ni bir marta aniqlaydi (ishonchli proksilar hisobga olingan)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.client_ip = client_ip(request)
        return self.get_response(request)


class GlobalRateLimitMiddleware:
    """Har bir IP uchun umumiy so'rovlar limiti — ilova darajasidagi oxirgi himoya chizig'i.

    Asosiy DDoS himoyasi nginx/Cloudflare'da (deploy/nginx.conf). Bu middleware ular chetlab
    o'tilganda yoki noto'g'ri sozlanganda ilovani va bazani ortiqcha yukdan saqlaydi.
    """

    EXEMPT_PREFIXES = ("/static/", "/favicon.ico", "/healthz/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.GLOBAL_RATE_LIMIT_ENABLED and not request.path.startswith(self.EXEMPT_PREFIXES):
            result = ratelimit.hit("global_ip", request.client_ip)
            if not result.allowed:
                if result.count == ratelimit.get_limit("global_ip").limit + 1:
                    security_log.warning("Global rate limit: ip=%s path=%s", request.client_ip, request.path)
                response = HttpResponse("Juda ko'p so'rov. Birozdan keyin qayta urinib ko'ring.",
                                        status=429, content_type="text/plain; charset=utf-8")
                response["Retry-After"] = str(result.retry_after)
                return response
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """Django o'zi qo'ymaydigan qo'shimcha xavfsizlik sarlavhalari."""

    PERMISSIONS_POLICY = ("camera=(), microphone=(), geolocation=(), payment=(), usb=(), "
                          "interest-cohort=(), browsing-topics=()")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Permissions-Policy", self.PERMISSIONS_POLICY)
        response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            # Shaxsiy ma'lumotli sahifalar brauzer/proksi keshida qolmasin.
            response.setdefault("Cache-Control", "private, no-store")
        return response
