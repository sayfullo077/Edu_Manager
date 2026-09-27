"""Kesh (Redis) asosidagi rate limiter.

Fixed-window algoritmi: har bir kalit uchun `window` soniyalik oynada `limit` tagacha urinish.
Redis'da `add` + `incr` atomar, shuning uchun bir nechta gunicorn worker/server orasida ham to'g'ri ishlaydi.
Limitlar `settings.RATE_LIMITS` da nom bilan saqlanadi — kodda raqam yozilmaydi.
"""

import hashlib
import time
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache


@dataclass(frozen=True)
class Limit:
    limit: int
    window: int  # soniya


@dataclass(frozen=True)
class Result:
    allowed: bool
    count: int
    retry_after: int


class RateLimited(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        minutes = max(1, round(retry_after / 60))
        super().__init__(f"Juda ko'p urinish. {minutes} daqiqadan keyin qayta urinib ko'ring.")


def get_limit(name: str) -> Limit:
    limit, window = settings.RATE_LIMITS[name]
    return Limit(limit, window)


def _key(name: str, ident: str, window: int) -> tuple[str, int]:
    now = int(time.time())
    bucket = now // window
    # Identifikator (telefon, IP) keshda ochiq saqlanmasin.
    digest = hashlib.sha256(ident.encode()).hexdigest()[:24]
    return f"rl:{name}:{digest}:{bucket}", window - (now % window)


def hit(name: str, ident: str) -> Result:
    """Urinishni hisoblaydi va limitdan oshganini qaytaradi."""
    cfg = get_limit(name)
    key, retry_after = _key(name, ident, cfg.window)
    if cache.add(key, 1, cfg.window + 1):
        count = 1
    else:
        try:
            count = cache.incr(key)
        except ValueError:  # kalit shu orada muddati tugab o'chdi
            cache.set(key, 1, cfg.window + 1)
            count = 1
    return Result(count <= cfg.limit, count, retry_after)


def peek(name: str, ident: str) -> Result:
    """Hisoblamasdan tekshiradi (masalan, faqat muvaffaqiyatsiz parolni sanash uchun)."""
    cfg = get_limit(name)
    key, retry_after = _key(name, ident, cfg.window)
    count = cache.get(key, 0)
    return Result(count < cfg.limit, count, retry_after)


def reset(name: str, ident: str) -> None:
    cfg = get_limit(name)
    key, _ = _key(name, ident, cfg.window)
    cache.delete(key)


def enforce(name: str, ident: str) -> None:
    result = hit(name, ident)
    if not result.allowed:
        raise RateLimited(result.retry_after)
