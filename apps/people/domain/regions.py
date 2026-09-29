"""O'zbekiston hududlari: viloyatlar ro'yxati (manzil formasidagi tanlagich uchun).

Tuman va mahallalar juda ko'p va o'zgarib turadi — ular erkin matn, avval kiritilganlaridan taklif qilinadi.
"""

REGIONS = (
    "Andijon viloyati",
    "Buxoro viloyati",
    "Farg'ona viloyati",
    "Jizzax viloyati",
    "Namangan viloyati",
    "Navoiy viloyati",
    "Qashqadaryo viloyati",
    "Qoraqalpog'iston Respublikasi",
    "Samarqand viloyati",
    "Sirdaryo viloyati",
    "Surxondaryo viloyati",
    "Toshkent shahri",
    "Toshkent viloyati",
    "Xorazm viloyati",
)


def region_choices(current: str = "") -> list[tuple[str, str]]:
    """Tanlagich variantlari. Ro'yxatda yo'q eski qiymat ham yo'qolmasin — u ham ko'rsatiladi."""
    choices = [("", "— Tanlang —"), *((r, r) for r in REGIONS)]
    if current and current not in REGIONS:
        choices.append((current, current))
    return choices
