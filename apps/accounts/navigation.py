"""Har bir rol uchun sidebar menyusi.

`slug=None` — bosh sahifa. Qolgan bo'limlar tayyor bo'lguncha "tez orada" sahifasini ochadi.
"""

from dataclasses import dataclass, field

from .models import Role


@dataclass(frozen=True)
class NavItem:
    label: str
    icon: str
    slug: str | None = None
    children: tuple["NavItem", ...] = field(default_factory=tuple)


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
            NavItem("O'quvchilar", "graduation", "students"),
            NavItem("Ota-onalar", "users", "guardians"),
            NavItem("Shartnomalar", "file", "contracts"),
            NavItem("Dars jadvali", "calendar", "timetable"),
        ]),
        ("Xodimlar", [NavItem("O'qituvchilar", "briefcase", "teachers")]),
        ("Oyliklar", [NavItem("Oylik hisob-kitob", "wallet", "payroll")]),
        ("Yotoqxona", [NavItem("Davomat", "bed", "dorm-attendance")]),
    ],
    Role.RECEPTION: [
        (None, [NavItem("Bosh sahifa", "home")]),
        ("Ta'lim bo'limi", [
            NavItem("O'quvchilar", "graduation", "students"),
            NavItem("Ota-onalar", "users", "guardians"),
            NavItem("Shartnomalar", "file", "contracts"),
        ]),
        ("Moliya", [
            NavItem("Kassa", "wallet", "cashbox"),
            NavItem("To'lovlar", "receipt", "payments"),
            NavItem("Tranzaksiyalar", "arrows", "transactions"),
            NavItem("Bank hisobi", "bank", "bank"),
            NavItem("To'lov grafiklari", "calendar", "invoices"),
            NavItem("Qarzdorlar", "alert", "debtors"),
            NavItem("Xarajatlar va byudjet", "chart", "budget"),
        ]),
        ("Yotoqxona", [
            NavItem("Xonalar", "bed", "dorm-rooms"),
            NavItem("Yotoqxona to'lovlari", "receipt", "dorm-invoices"),
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
