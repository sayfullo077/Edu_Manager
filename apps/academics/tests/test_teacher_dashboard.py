from datetime import date, datetime, time

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.academics import selectors
from apps.academics.models import Group, GroupMembership, GroupSubject, Lesson, Subject, TimeSlot
from apps.accounts.models import Role, User, UserRole
from apps.people.models import Student, Teacher
from conftest import make_staff

FRIDAY = date(2026, 10, 2)


@pytest.fixture
def setup(branch, year, school_class):
    user = User.objects.create_user("998901112233", "Str0ng-pass-123", last_name="Ustoz", first_name="Test")
    UserRole.objects.create(user=user, role=Role.TEACHER, branch=branch)
    t = Teacher.objects.create(user=user, branch=branch)
    by = make_staff(branch, Role.HEAD_TEACHER, "998900000196")
    it = Subject.objects.create(name="IT")
    whole = Group.objects.create(branch=branch, academic_year=year, school_class=school_class, code="IT-4A")
    sub = Group.objects.create(branch=branch, academic_year=year, school_class=school_class, code="IT-Aniq1-01",
                               kind=Group.Kind.SUBSET, capacity=30)
    for g in (whole, sub):
        GroupSubject.objects.create(group=g, subject=it, teacher=t)
    for n in ("Ali", "Bek"):
        s = Student.objects.create(branch=branch, last_name="Test", first_name=n, birth_date=date(2016, 1, 1),
                                   gender="M", grade=4, joined_at=date(2026, 9, 2), school_class=school_class)
        GroupMembership.objects.create(group=sub, student=s, joined_at=date(2026, 9, 2))
    slots = [TimeSlot.objects.create(branch=branch, number=i, start=time(h, 0), end=time(h, 45))
             for i, h in ((1, 8), (2, 10), (3, 12))]
    for slot, g in zip(slots, (whole, sub, sub), strict=True):  # juma (5) — 3 dars
        Lesson.objects.create(branch=branch, academic_year=year, group=g, subject=it, teacher=t, weekday=5,
                              slot=slot, valid_from=date(2026, 9, 2), created_by=by)
    Lesson.objects.create(branch=branch, academic_year=year, group=whole, subject=it, teacher=t, weekday=1,
                          slot=slots[0], valid_from=date(2026, 9, 2), created_by=by)
    return {"t": t, "user": user}


def test_dashboard_data(branch, setup, monkeypatch):
    now = timezone.make_aware(datetime.combine(FRIDAY, time(10, 20)))
    monkeypatch.setattr(timezone, "localtime", lambda *a: now)
    d = selectors.teacher_dashboard(branch, setup["t"], FRIDAY)
    assert [x["state"] for x in d["today_lessons"]] == ["done", "now", "waiting"]
    assert d["next_lesson"].slot.number == 3
    assert d["week_lessons"] == 4                        # 3 juma + 1 dushanba
    assert [g.code for g in d["groups"]] == ["IT-Aniq1-01"]   # faqat tanlov guruhlari (asl tizimdagidek)
    assert d["students"] == 2 and d["groups"][0].n_members == 2


def test_sunday_has_no_lessons(branch, setup):
    assert selectors.lessons_on(branch, setup["t"], date(2026, 10, 4)) == []


def test_home_renders_for_teacher(client, setup):
    client.force_login(setup["user"])
    resp = client.get(reverse("core:home"))
    assert resp.status_code == 200 and "Bugungi darslar" in resp.content.decode()
    assert resp.context["teacher"] == setup["t"]


def test_teacher_without_profile(client, branch):
    client.force_login(make_staff(branch, Role.TEACHER, "998900000197"))
    resp = client.get(reverse("core:home"))
    assert resp.status_code == 200 and "profili topilmadi" in resp.content.decode()


def test_superadmin_picks_teacher(client, branch, setup):
    admin = User.objects.create_superuser("998900000198", "Str0ng-pass-123", last_name="Admin", first_name="Tizim")
    client.force_login(admin)
    client.post(reverse("accounts:superadmin_view_as"), {"role": Role.TEACHER, "branch": branch.pk})
    resp = client.get(reverse("core:home"))
    assert resp.status_code == 200 and resp.context["teacher"] is None
    assert setup["t"] in resp.context["preview_teachers"]
    resp = client.get(reverse("core:home"), {"teacher": setup["t"].pk})
    assert resp.context["teacher"] == setup["t"]
    assert client.get(reverse("core:home")).context["teacher"] == setup["t"]  # tanlov eslab qolinadi


def test_my_schedule(client, setup):
    client.force_login(setup["user"])
    url = reverse("academics:my_schedule")
    resp = client.get(url, {"week": "2026-10-02"})
    assert resp.status_code == 200 and resp.context["grid"]["total"] == 4
    assert resp.context["monday"] == date(2026, 9, 28)
    friday = resp.context["week_days"][4]
    assert [slot.number for slot, _ in friday["lessons"]] == [1, 2, 3]
    assert "IT-Aniq1-01" in resp.content.decode()
    assert client.get(url, {"week": "xato"}).status_code == 200  # noto'g'ri sana — joriy hafta


def test_my_schedule_only_teacher(staff_client):
    assert staff_client.get(reverse("academics:my_schedule")).status_code in (302, 403)


def test_my_groups_and_membership(client, branch, year, school_class, setup):
    from apps.academics.models import GroupMembership as GM
    client.force_login(setup["user"])
    resp = client.get(reverse("academics:my_groups"))
    groups = resp.context["groups"]
    assert [g.code for g in groups] == ["IT-Aniq1-01"] and groups[0].my_subjects[0].name == "IT"
    g = groups[0]
    newbie = Student.objects.create(branch=branch, last_name="Test", first_name="Yangi", birth_date=date(2016, 1, 1),
                                    gender="M", grade=4, joined_at=date(2026, 9, 2), school_class=school_class)
    url = reverse("academics:my_group_detail", args=[g.pk])
    resp = client.get(url)
    assert [s.first_name for s in resp.context["candidates"]] == ["Yangi"]
    assert resp.context["stats"] == {"total": 3, "assigned": 2, "free": 1, "seats": 28}
    client.post(reverse("academics:my_group_add", args=[g.pk]), {"student": newbie.pk})
    assert GM.objects.filter(group=g, student=newbie, left_at__isnull=True).exists()
    m = GM.objects.get(group=g, student=newbie)
    client.post(reverse("academics:my_group_remove", args=[g.pk, m.pk]))
    m.refresh_from_db()
    assert m.left_at is not None  # o'chirilmaydi — tarixda qoladi
    assert client.get(url).context["candidates"].filter(pk=newbie.pk).exists()  # nomzodlarga qaytdi


def test_one_group_per_subject(branch, year, school_class, setup):
    from django.core.exceptions import ValidationError

    from apps.academics.services import groups as group_service
    t = setup["t"]
    it = Subject.objects.get(name="IT")
    other = Group.objects.create(branch=branch, academic_year=year, school_class=school_class, code="IT-Aniq1-02",
                                 kind=Group.Kind.SUBSET)
    GroupSubject.objects.create(group=other, subject=it, teacher=t)
    ali = Student.objects.get(first_name="Ali")
    assert not selectors_candidates(other).filter(pk=ali.pk).exists()
    with pytest.raises(ValidationError):
        group_service.add_members(other, students=[ali], on=date(2026, 10, 3), by=setup["user"])


def selectors_candidates(group):
    return selectors.member_candidates(group)


def test_other_teacher_cannot_manage(client, branch, setup):
    other = User.objects.create_user("998901112234", "Str0ng-pass-123", last_name="Boshqa", first_name="Ustoz")
    UserRole.objects.create(user=other, role=Role.TEACHER, branch=branch)
    Teacher.objects.create(user=other, branch=branch)
    client.force_login(other)
    g = Group.objects.get(code="IT-Aniq1-01")
    assert client.get(reverse("academics:my_group_detail", args=[g.pk])).status_code == 404
    assert client.post(reverse("academics:my_group_add", args=[g.pk]), {"student": 1}).status_code == 404


def test_superadmin_preview_can_assign(client, branch, school_class, setup):
    from apps.academics.models import GroupMembership as GM
    admin = User.objects.create_superuser("998900000199", "Str0ng-pass-123", last_name="Admin", first_name="Tizim")
    client.force_login(admin)
    client.post(reverse("accounts:superadmin_view_as"), {"role": Role.TEACHER, "branch": branch.pk})
    client.get(reverse("core:home"), {"teacher": setup["t"].pk})  # o'qituvchi tanlandi
    g = Group.objects.get(code="IT-Aniq1-01")
    newbie = Student.objects.create(branch=branch, last_name="Test", first_name="Yangi", birth_date=date(2016, 1, 1),
                                    gender="M", grade=4, joined_at=date(2026, 9, 2), school_class=school_class)
    assert client.get(reverse("academics:my_group_detail", args=[g.pk])).context["can_edit"]
    client.post(reverse("academics:my_group_add", args=[g.pk]), {"student": newbie.pk})
    assert GM.objects.filter(group=g, student=newbie, left_at__isnull=True).exists()


# ---------- Sinf rahbarlik ----------

def test_homeroom_list_and_day_save(client, branch, school_class, setup, monkeypatch):
    from apps.academics.models import ClassAttendance
    monkeypatch.setattr(timezone, "localdate", lambda *a: FRIDAY)
    school_class.homeroom_teacher = setup["t"]
    school_class.save()
    client.force_login(setup["user"])
    resp = client.get(reverse("academics:my_homeroom"))
    c = resp.context["classes"][0]
    assert (c.n_students, c.att_state) == (2, "none")
    url = reverse("academics:my_homeroom_class", args=[school_class.pk])
    sheet = client.get(url).context["sheet"]
    ali, bek = (x["student"] for x in sheet)
    client.post(url, {"date": "2026-10-02", f"s{ali.pk}": "B", f"n{ali.pk}": "",
                      f"s{bek.pk}": "S", f"n{bek.pk}": "Kasal"})
    assert dict(ClassAttendance.objects.values_list("student__first_name", "status")) == {"Ali": "B", "Bek": "S"}
    assert ClassAttendance.objects.get(student=bek).note == "Kasal"
    assert client.get(reverse("academics:my_homeroom")).context["classes"][0].att_state == "full"
    # belgini olib tashlash
    client.post(url, {"date": "2026-10-02", f"s{ali.pk}": "", f"s{bek.pk}": "S", f"n{bek.pk}": "Kasal"})
    assert ClassAttendance.objects.count() == 1
    # oylik statistika va Excel
    st = client.get(url, {"tab": "month", "month": "2026-10"}).context["stats"]
    assert st["totals"]["S"] == 1 and st["rows"][1]["percent"] == 0
    assert client.get(url, {"tab": "week"}).context["grid"]["total"] == 4
    resp = client.get(reverse("academics:my_homeroom_export", args=[school_class.pk]), {"month": "2026-10"})
    assert resp.status_code == 200


def test_homeroom_rules(branch, school_class, setup, monkeypatch):
    from django.core.exceptions import ValidationError

    from apps.academics.services import class_attendance
    monkeypatch.setattr(timezone, "localdate", lambda *a: FRIDAY)
    ali = Student.objects.get(first_name="Ali")
    with pytest.raises(ValidationError):  # kelgusi kun
        class_attendance.save_day(school_class, day=date(2026, 10, 5), rows={ali.pk: ("B", "")}, by=setup["user"])
    with pytest.raises(ValidationError):  # izoh bor, belgi yo'q
        class_attendance.save_day(school_class, day=FRIDAY, rows={ali.pk: ("", "Sabab")}, by=setup["user"])
    other = Student.objects.create(branch=branch, last_name="Test", first_name="Begona", birth_date=date(2016, 1, 1),
                                   gender="M", grade=4, joined_at=date(2026, 9, 2))
    with pytest.raises(ValidationError):  # boshqa sinf o'quvchisi
        class_attendance.save_day(school_class, day=FRIDAY, rows={other.pk: ("B", "")}, by=setup["user"])


def test_homeroom_not_mine_404(client, school_class, setup):
    client.force_login(setup["user"])  # rahbar emas
    assert client.get(reverse("academics:my_homeroom_class", args=[school_class.pk])).status_code == 404


def test_salary_guide(client, branch, setup):
    from apps.payroll.selectors import payroll_settings
    cfg = payroll_settings(branch)
    cfg.certificate_percent, cfg.homeroom_rate = 25, 40000
    cfg.save()
    client.force_login(setup["user"])
    resp = client.get(reverse("academics:my_salary_guide"))
    html = resp.content.decode()
    assert resp.status_code == 200 and "Ish haqi qoidalari" in html
    assert "+25%" in html and "40\xa0000 so'm" in html  # foizlar sozlamadan
    assert resp.context["pay"] is not None  # o'qituvchining shu oydagi shaxsiy hisobi
