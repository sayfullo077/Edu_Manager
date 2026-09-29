import pytest
from django.urls import reverse

from apps.accounts.models import ImpersonationLog, Role, User
from conftest import make_staff


@pytest.fixture
def su(db):
    return User.objects.create_superuser("998900000000", "Str0ng-pass-123", last_name="Admin", first_name="Bosh")


@pytest.fixture
def su_client(client, su):
    client.force_login(su)
    return client


def test_superadmin_home_redirects_to_panel(su_client, branch):
    resp = su_client.get(reverse("core:home"))
    assert resp.url == reverse("accounts:superadmin")
    assert su_client.get(resp.url).status_code == 200


def test_view_as_any_role_without_being_assigned(su_client, branch, su):
    su_client.post(reverse("accounts:superadmin_view_as"), {"role": Role.RECEPTION, "branch": branch.pk})
    home = su_client.get(reverse("core:home")).content.decode()
    assert "Filial byudjeti" in home  # Reception dashboard
    assert "Superadmin ko'rinishi" in home
    assert su.roles.count() == 0  # bazada rol yaratilmadi
    su_client.post(reverse("accounts:superadmin_view_as"), {"role": Role.HEAD_TEACHER, "branch": branch.pk})
    assert su_client.get(reverse("finance:dashboard")).status_code == 403  # Zavuch moliyani ko'rmaydi
    assert ImpersonationLog.objects.filter(mode="role").count() == 2
    assert ImpersonationLog.objects.filter(mode="role", ended_at__isnull=False).count() == 1


def test_impersonate_user_and_return(su_client, branch, reception, su):
    su_client.post(reverse("accounts:superadmin_impersonate", args=[reception.pk]))
    page = su_client.get(reverse("people:student_list")).content.decode()
    assert "qiyofasidasiz" in page and reception.full_name in page

    # "Chiqish" bosilsa — tizimdan chiqmaydi, superadmin paneliga qaytadi
    resp = su_client.post(reverse("accounts:logout"))
    assert resp.url == reverse("accounts:superadmin")
    assert int(su_client.session["_auth_user_id"]) == su.pk
    log = ImpersonationLog.objects.get(mode="user")
    assert log.target == reception and log.ended_at is not None
    assert log.actions == 0  # qaytish/chiqish "amal" emas


def test_actions_during_impersonation_are_audited(su_client, branch, reception, school_class):
    su_client.post(reverse("accounts:superadmin_impersonate", args=[reception.pk]))
    su_client.post(reverse("people:student_toggle_flag", args=[999, "in_erp"]))
    assert ImpersonationLog.objects.get(mode="user").actions >= 1


def test_cannot_impersonate_admins(su_client, branch):
    other = User.objects.create_superuser("998900000009", "x", last_name="Boshqa", first_name="Admin")
    staff = User.objects.create_user("998900000008", "x", last_name="Staff", first_name="X", is_staff=True)
    for target in (other, staff):
        su_client.post(reverse("accounts:superadmin_impersonate", args=[target.pk]))
        assert "su_impersonate" not in su_client.session


def test_admin_panel_closed_while_impersonating(su_client, branch, reception):
    su_client.post(reverse("accounts:superadmin_impersonate", args=[reception.pk]))
    assert su_client.get(reverse("admin:index")).status_code == 302


def test_regular_users_cannot_use_superadmin(client, branch, reception, teacher_user):
    client.force_login(reception)
    assert client.get(reverse("accounts:superadmin")).status_code == 403
    assert client.post(reverse("accounts:superadmin_impersonate", args=[teacher_user.pk])).status_code == 403
    assert client.post(reverse("accounts:superadmin_view_as"),
                       {"role": Role.HEAD_TEACHER, "branch": branch.pk}).status_code == 403
    assert client.post(reverse("accounts:superadmin_stop")).status_code == 403
    # Qo'lda sessiyaga yozilgan kalit ham ishlamaydi (faqat superadmin uchun)
    session = client.session
    session["su_impersonate"] = {"user_id": teacher_user.pk}
    session.save()
    page = client.get(reverse("people:student_list")).content.decode()
    assert reception.full_name in page and "qiyofasidasiz" not in page


def test_impersonation_ends_if_superadmin_rights_removed(su_client, branch, reception, su):
    su_client.post(reverse("accounts:superadmin_impersonate", args=[reception.pk]))
    User.objects.filter(pk=su.pk).update(is_superuser=False)
    page = su_client.get(reverse("core:home")).content.decode()
    assert "qiyofasidasiz" not in page


def test_cannot_nest_impersonation(su_client, branch, reception, teacher_user):
    su_client.post(reverse("accounts:superadmin_impersonate", args=[reception.pk]))
    assert su_client.get(reverse("accounts:superadmin")).status_code == 403
    assert su_client.post(reverse("accounts:superadmin_impersonate", args=[teacher_user.pk])).status_code == 403


def test_head_teacher_role_switch_still_works(client, branch):
    user = make_staff(branch, Role.HEAD_TEACHER, "998900000155")
    client.force_login(user)
    assert client.get(reverse("people:student_list")).status_code == 200


def test_cannot_change_password_while_impersonating(su_client, branch, reception):
    su_client.post(reverse("accounts:superadmin_impersonate", args=[reception.pk]))
    su_client.post(reverse("accounts:settings"), {
        "old_password": "Str0ng-pass-123", "new_password1": "Boshqa-parol-99!", "new_password2": "Boshqa-parol-99!"})
    reception.refresh_from_db()
    assert reception.check_password("Str0ng-pass-123")
