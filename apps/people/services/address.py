"""Manzil ma'lumotnomasi: forma orqali kiritilgan yangi mahalla bazaga yoziladi (keyingi safar ro'yxatda chiqadi)."""

import logging

from ..models import District, Mahalla

logger = logging.getLogger(__name__)


def remember_mahalla(*, region: str, district: str, mahalla: str) -> None:
    """Tuman ma'lumotnomada bo'lsa va bunday mahalla hali yo'q bo'lsa — qo'shadi. Tuman noma'lum bo'lsa, hech narsa."""
    name = " ".join((mahalla or "").split())
    if not (region and district and name):
        return
    d = District.objects.filter(region=region, name__iexact=district.strip()).first()
    if d is None or Mahalla.objects.filter(district=d, name__iexact=name).exists():
        return
    Mahalla.objects.create(district=d, name=name)
    logger.info("Yangi mahalla ma'lumotnomaga qo'shildi: %s / %s", d.name, name)
