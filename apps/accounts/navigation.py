"""Har bir rol uchun sidebar menyusi.

- `url_name` bor band — haqiqiy sahifa.
- Faqat `slug` bor band — bo'lim hali qurilmagan, "tez orada" sahifasini ochadi.
- Hech biri yo'q — bosh sahifa.
"""

from dataclasses import dataclass

from django.conf import settings
from django.urls import reverse
from django.utils.text import slugify

from .models import Role


@dataclass(frozen=True)
class NavItem:
    label: str
    icon: str
    slug: str | None = None
    url_name: str | None = None

    @property
    def url(self) -> str:
        if self.url_name:
            return reverse(self.url_name)
        if self.slug:
            return reverse("core:section", args=[self.slug])
        return reverse("core:home")


STUDENTS = NavItem("O'quvchilar", "graduation", "students", "people:student_list")
GUARDIANS = NavItem("Ota-onalar", "users", "guardians", "people:guardian_list")
CONTRACTS = NavItem("Shartnomalar", "file", "contracts", "contracts:contract_list")
# Hozircha yopiq (settings.BUDGET_PAGE_ENABLED) — "Bu bo'lim tayyorlanmoqda" sahifasi ochiladi
BUDGET = NavItem("Xarajatlar va byudjet", "chart", "budget",
                 "finance:budget_edit" if settings.BUDGET_PAGE_ENABLED else None)

NAVIGATION: dict[str, list[tuple[str | None, list[NavItem]]]] = {
    Role.TEACHER: [
        (None, [
            NavItem("Bosh sahifa", "home"),
            NavItem("Mening jadvalim", "calendar", "my-schedule"),
            NavItem("Guruhlarim", "users", "my-groups"),
            NavItem("Sinf rahbarlik", "school", "homeroom"),
        ]),
        ("Oylik", [
            NavItem("Oyligim", "wallet", "my-salary"),
            NavItem("Oylik qanday hisoblanadi", "info", "salary-guide"),
        ]),
    ],
    Role.HEAD_TEACHER: [
        (None, [NavItem("Bosh sahifa", "home")]),
        ("Ta'lim bo'limi", [
            STUDENTS,
            GUARDIANS,
            NavItem("Sinflar va guruhlar", "school", "classes"),
            CONTRACTS,
            NavItem("Dars jadvali", "calendar", "timetable"),
        ]),
        ("Xodimlar", [NavItem("O'qituvchilar", "briefcase", "teachers")]),
        ("Oyliklar", [NavItem("Oylik hisob-kitob", "wallet", "payroll")]),
        ("Yotoqxona", [NavItem("Davomat", "bed", "dorm-attendance")]),
    ],
    Role.RECEPTION: [
        (None, [NavItem("Bosh sahifa", "home")]),
        ("Ta'lim bo'limi", [
            STUDENTS,
            GUARDIANS,
            CONTRACTS,
        ]),
        ("Kirim", [
            NavItem("Kassa", "wallet", "cashbox", "finance:cashbox"),
            NavItem("To'lovlar", "receipt", "payments", "finance:payment_list"),
            NavItem("Tranzaksiyalar", "arrows", "transactions", "finance:transaction_list"),
            NavItem("Bank hisobi", "bank", "bank", "finance:bank_account"),
            NavItem("To'lov grafiklari", "calendar", "invoices", "finance:invoice_list"),
            NavItem("Qarzdorlar", "alert", "debtors", "finance:debtor_list"),
            BUDGET,
        ]),
        ("Yotoqxona", [
            NavItem("Boshqaruv paneli", "chart", "dorm", "dorm:dashboard"),
            NavItem("Xonalar", "bed", "dorm-rooms", "dorm:room_list"),
            NavItem("To'lov grafiklari", "calendar", "dorm-invoices"),
            NavItem("Qarzdorlar", "alert", "dorm-debtors"),
            NavItem("Mulkdor to'lovlari", "wallet", "dorm-landlord"),
        ]),
    ],
}


def navigation_for(role: str | None):
    return NAVIGATION.get(role, [])


def find_item(role: str | None, slug: str) -> NavItem | None:
    for _, items in navigation_for(role):
        for item in items:
            if item.slug == slug:
                return item
    return None


GROUP_ICONS = {
    "Ta'lim bo'limi": "graduation",
    "Kirim": "wallet",
    "Yotoqxona": "home",
    "Oylik": "wallet",
    "Oyliklar": "wallet",
    "Xodimlar": "briefcase",
}


def build_menu(role: str | None, path: str) -> list[dict]:
    """Shablon uchun tayyor menyu: bandlar (url, faollik) va yig'iladigan guruhlar (ikon, ochiqligi)."""
    home = reverse("core:home")
    groups = [(title, [(item, item.url) for item in items]) for title, items in navigation_for(role)]
    # Faqat eng aniq (eng uzun) mos manzil faol: /dorm/rooms/ da "/dorm/" (Boshqaruv paneli) belgilanmasin
    matches = [url for _, items in groups for _, url in items
               if (path == url if url == home else path.startswith(url))]
    best = max(matches, key=len, default=None)
    menu = []
    for title, items in groups:
        entries = [{"item": item, "url": url, "active": url == best} for item, url in items]
        menu.append({
            "title": title, "items": entries, "icon": GROUP_ICONS.get(title, "file"),
            "key": slugify(title or "main"), "active": any(e["active"] for e in entries),
        })
    return menu
