"""Shartnoma matni: shablon + ma'lumotlar → bloklar (sarlavha, bo'lim, xatboshi...).

Shablon belgilash qoidalari (har bir qator — alohida blok):
    # Matn        — hujjat sarlavhasi (markazda, katta)
    ## Matn       — bo'lim sarlavhasi ("1. Shartnoma predmeti.")
    ### Matn      — kichik sarlavha (markazda)
    >> Matn       — o'ngga tekislangan qator (sana)
    - Matn        — ro'yxat bandi
    **qalin**     — qator ichida qalin matn
    {{ kalit }}   — o'rinbosar (PLACEHOLDERS dagi kalitlar)
Bo'sh qator — e'tiborsiz. Barcha matn HTML sifatida escape qilinadi: shablon yoki ma'lumotdagi `<script>` va h.k.
ishlamaydi. Qiymati bo'sh o'rinbosar — qo'lda to'ldirish uchun "________".
"""

import re

from django.utils.html import escape
from django.utils.safestring import mark_safe

PLACEHOLDERS: dict[str, str] = {
    "raqam": "Shartnoma raqami (CTR-2026-001)",
    "sana": "Shartnoma tuzilgan sana",
    "oquv_yili": "O'quv yili (2026-2027)",
    "maktab": "Maktab nomi",
    "yuridik_nomi": "Yuridik nomi («...» MCHJ)",
    "filial": "Filial nomi",
    "filial_manzili": "Filial manzili",
    "direktor": "Direktor F.I.Sh.",
    "maktab_telefon": "Filial telefoni",
    "bank_hisob": "Hisob raqami (H/R)",
    "bank_nomi": "Bank nomi",
    "mfo": "Bank MFO",
    "stir": "STIR (INN)",
    "vasiy": "Vasiy (buyurtmachi) F.I.Sh.",
    "vasiy_telefon": "Vasiy telefoni",
    "oquvchi": "O'quvchi F.I.Sh.",
    "oquvchi_kodi": "O'quvchi kodi (STD-...)",
    "sinf": "Sinf nomi (3-B, Aniq1)",
    "sinf_darajasi": "Sinf darajasi (9-sinf)",
    "boshlanish": "Boshlanish sanasi",
    "tugash": "Tugash sanasi",
    "tarif": "Oylik tarif (chegirmasiz)",
    "chegirma": "Chegirma (%)",
    "oylik_tolov": "Oylik to'lov (chegirma bilan)",
    "oylar": "Oylar soni",
    "jami": "Jami summa (oylik × oylar)",
}

BLANK = "________"
_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_PREFIXES = (("### ", "subtitle"), ("## ", "heading"), ("# ", "title"), (">> ", "right"), ("- ", "item"))


def fill(text: str, data: dict) -> str:
    """O'rinbosarlarni qiymat bilan almashtiradi (hali escape qilinmagan matn)."""
    def repl(m):
        key = m.group(1)
        if key not in PLACEHOLDERS:
            return m.group(0)  # noma'lum kalit — o'zgarishsiz ko'rinadi (shablon muallifi xatoni ko'rsin)
        value = str(data.get(key) or "").strip()
        return value or BLANK
    return _PLACEHOLDER.sub(repl, text)


def _inline(text: str) -> str:
    html = escape(text)
    return _BOLD.sub(r"<b>\1</b>", html)


def render_blocks(body: str, data: dict) -> list[dict]:
    """[{"kind": "title|subtitle|heading|right|item|para", "html": SafeString}, ...]"""
    blocks = []
    for raw in (body or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        kind = "para"
        for prefix, name in _PREFIXES:
            if line.startswith(prefix):
                kind, line = name, line[len(prefix):]
                break
        blocks.append({"kind": kind, "html": mark_safe(_inline(fill(line, data)))})  # noqa: S308 — escape qilingan
    return blocks


def unknown_placeholders(body: str) -> list[str]:
    return sorted({m.group(1) for m in _PLACEHOLDER.finditer(body or "") if m.group(1) not in PLACEHOLDERS})
