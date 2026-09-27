import ipaddress

from django.conf import settings


def client_ip(request) -> str:
    """Mijozning haqiqiy IP manzili.

    X-Forwarded-For sarlavhasini har kim soxtalashtira oladi, shuning uchun unga faqat
    oldimizda turgan ishonchli proksilar soni (TRUSTED_PROXY_COUNT) bo'yicha ishonamiz:
    nginx bitta bo'lsa — 1, Cloudflare + nginx bo'lsa — 2. Proksi yo'q bo'lsa — 0 (REMOTE_ADDR).
    """
    remote = request.META.get("REMOTE_ADDR", "")
    hops = settings.TRUSTED_PROXY_COUNT
    if hops <= 0:
        return remote
    chain = [p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()]
    if len(chain) < hops:
        return remote
    candidate = chain[-hops]
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return remote
    return candidate
