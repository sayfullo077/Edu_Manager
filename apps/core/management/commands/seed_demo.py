import secrets
from datetime import date

import environ
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Role, User, UserRole
from apps.core.models import AcademicYear, Branch, SchoolSettings

CREDENTIALS_FILE = settings.BASE_DIR / "demo_credentials.txt"

# Soxta raqamlar — haqiqiy odamlarga tegishli emas.
DEMO_USERS = [
    ("998900000001", "Karimov", "Aziz", [Role.TEACHER, Role.HEAD_TEACHER, Role.RECEPTION]),
    ("998900000002", "Rahimova", "Dilnoza", [Role.TEACHER]),
    ("998900000003", "Tursunov", "Bekzod", [Role.HEAD_TEACHER]),
    ("998900000004", "Yusupova", "Malika", [Role.RECEPTION]),
]


class Command(BaseCommand):
    help = "Demo ma'lumotlar: maktab sozlamalari, filial, o'quv yili va rollari bor foydalanuvchilar."

    @transaction.atomic
    def handle(self, *args, **options):
        password = environ.Env().str("DEMO_PASSWORD", default="") or self._local_password()

        school = SchoolSettings.load()
        school.name, school.short_name = "Maktab", "Maktab"
        school.tagline = "Xususiy maktab boshqaruv platformasi"
        school.brand_color = "#08915E"
        school.save()

        branch, _ = Branch.objects.get_or_create(name="Oltiariq filiali")
        AcademicYear.objects.update_or_create(
            name="2026-2027",
            defaults={"start_date": date(2026, 9, 2), "end_date": date(2027, 6, 30), "is_current": True},
        )

        for phone, last, first, roles in DEMO_USERS:
            user, _ = User.objects.get_or_create(phone=phone, defaults={"last_name": last, "first_name": first})
            user.set_password(password)
            user.save()
            for role in roles:
                UserRole.objects.get_or_create(user=user, role=role, branch=branch)

        admin, created = User.objects.get_or_create(
            phone="998900000000", defaults={"last_name": "Admin", "first_name": "Tizim",
                                            "is_staff": True, "is_superuser": True})
        admin.set_password(password)
        admin.save()

        self.stdout.write(self.style.SUCCESS(
            f"Tayyor. {len(DEMO_USERS) + 1} ta demo foydalanuvchi, parol: {CREDENTIALS_FILE.name} "
            f"(yoki DEMO_PASSWORD). SMS backend: {settings.SMS_BACKEND.rsplit('.', 1)[-1]}"
        ))

    def _local_password(self):
        """Parolni chatga yoki logga chiqarmaslik uchun gitignore qilingan faylda saqlaymiz."""
        if CREDENTIALS_FILE.exists():
            for line in CREDENTIALS_FILE.read_text().splitlines():
                if line.startswith("password="):
                    return line.split("=", 1)[1]
        password = "demo-" + secrets.token_urlsafe(9)
        lines = ["# Demo foydalanuvchilar (faqat lokal development uchun)", f"password={password}", ""]
        lines += [f"{phone}  {last} {first}  {', '.join(r.label for r in roles)}"
                  for phone, last, first, roles in DEMO_USERS]
        lines.append("998900000000  Admin (superuser, /admin/)")
        CREDENTIALS_FILE.write_text("\n".join(lines) + "\n")
        return password
