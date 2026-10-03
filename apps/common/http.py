"""HTTP yordamchilari."""

from django.utils.http import url_has_allowed_host_and_scheme


def safe_next(request, candidate: str | None, fallback: str) -> str:
    """Open redirect himoyasi: `?next=` faqat o'z saytimizdagi manzil bo'lsa ishlatiladi, aks holda `fallback`."""
    # Faqat o'z saytimizdagi mutlaq yo'l ("/..."): "abc" kabi nisbiy qiymatni redirect() view nomi deb
    # izlaydi va 500 beradi; "//evil.com" — boshqa sayt (url_has_allowed_host_and_scheme ham rad etadi).
    if (candidate and candidate.startswith("/") and not candidate.startswith("//")
            and url_has_allowed_host_and_scheme(candidate, allowed_hosts={request.get_host()},
                                                require_https=request.is_secure())):
        return candidate
    return fallback


def int_param(value, default: int | None = None) -> int | None:
    """So'rov parametrini butun songa aylantiradi; noto'g'ri qiymatda — `default` (500 xato o'rniga).

    ID sifatida bazaga uzatiladigan har qanday GET/POST qiymat shu orqali o'tadi.
    """
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default
