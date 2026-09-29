from datetime import date
from decimal import Decimal

import pytest
from django.core.cache import cache

from apps.academics.models import SchoolClass
from apps.accounts.models import Role, User, UserRole
from apps.core.models import AcademicYear, Branch


@pytest.fixture(autouse=True)
def _clear_cache():
    """Rate limit hisoblagichlari va keshlangan sozlamalar testlar orasida o'tib ketmasin."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _private_media(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def branch(db):
    return Branch.objects.create(name="Test filial")


@pytest.fixture
def other_branch(db):
    return Branch.objects.create(name="Boshqa filial")


@pytest.fixture
def year(db):
    return AcademicYear.objects.create(name="2026-2027", start_date=date(2026, 9, 2),
                                       end_date=date(2027, 6, 30), is_current=True)


@pytest.fixture
def school_class(branch, year):
    return SchoolClass.objects.create(branch=branch, academic_year=year, name="4-A", grade=4,
                                      monthly_tariff=Decimal("1750000"))


def make_staff(branch, role, phone):
    user = User.objects.create_user(phone, "Str0ng-pass-123", last_name="Xodim", first_name=role)
    UserRole.objects.create(user=user, role=role, branch=branch)
    return user


@pytest.fixture
def reception(branch):
    return make_staff(branch, Role.RECEPTION, "998900000104")


@pytest.fixture
def teacher_user(branch):
    return make_staff(branch, Role.TEACHER, "998900000102")


@pytest.fixture
def staff_client(client, reception):
    client.force_login(reception)
    return client
