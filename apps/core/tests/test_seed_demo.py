"""seed_demo toza bazada ishlashi kerak (deploy'da MVP sinovi uchun birinchi buyruq)."""

from django.core.management import call_command

from apps.accounts.models import Role, UserRole
from apps.people.models import Student


def test_seed_demo_on_empty_db(db, monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "Demo-test-parol-123")
    call_command("seed_demo", verbosity=0)
    assert Student.objects.exists()
    assert UserRole.objects.filter(role=Role.DIRECTOR).exists()
    call_command("seed_demo", verbosity=0)  # qayta ishga tushirish xatosiz (idempotent)
