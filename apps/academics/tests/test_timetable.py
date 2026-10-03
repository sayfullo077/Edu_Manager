from datetime import date, time, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.academics import selectors
from apps.academics.models import Group, GroupMembership, GroupSubject, Lesson, Room, SchoolClass, Subject, TimeSlot
from apps.academics.services import timetable
from apps.accounts.models import Role, User
from apps.people.models import Student, Teacher
from conftest import make_staff

MON = date(2026, 9, 7)  # dushanba


@pytest.fixture
def head(branch):
    return make_staff(branch, Role.HEAD_TEACHER, "998900000170")


@pytest.fixture
def head_client(client, head):
    client.force_login(head)
    return client


def teacher(branch, phone, name):
    user = User.objects.create_user(phone, "Str0ng-pass-123", last_name=name, first_name="T")
    return Teacher.objects.create(user=user, branch=branch)


@pytest.fixture
def env(branch, year, school_class):
    slots = timetable.ensure_slots(branch)
    t1, t2 = teacher(branch, "998900000171", "Birinchi"), teacher(branch, "998900000172", "Ikkinchi")
    it, math = Subject.objects.create(name="IT"), Subject.objects.create(name="Matematika")
    room = Room.objects.create(branch=branch, name="31-xona")
    g_it = Group.objects.create(branch=branch, academic_year=year, school_class=school_class, code="IT-4A")
    GroupSubject.objects.create(group=g_it, subject=it, teacher=t1)
    g_math = Group.objects.create(branch=branch, academic_year=year, school_class=school_class, code="MAT-4A")
    GroupSubject.objects.create(group=g_math, subject=math, teacher=t2)
    return {"slots": slots, "t1": t1, "t2": t2, "it": it, "math": math, "room": room, "g_it": g_it, "g_math": g_math}


def add(env, group, subject, *, weekday=1, slot=0, room=None, on=MON, by=None):
    return timetable.add_lesson(group=env[group], subject=env[subject], weekday=weekday, slot=env["slots"][slot],
                                room=room, on=on, by=by)


def test_default_bells_50_minutes(branch):
    slots = timetable.ensure_slots(branch)
    assert len(slots) == 8 and (slots[0].start, slots[0].end) == (time(8, 30), time(9, 20))
    assert slots[5].start == time(13, 5) and timetable.ensure_slots(branch) == slots  # qayta yaratilmaydi


def test_conflicts_are_blocked(env, head, branch, year, school_class):
    add(env, "g_it", "it", room=env["room"], by=head)
    with pytest.raises(ValidationError, match="sinfi bu vaqtda darsda"):  # bir sinfga ikki butun-sinf darsi
        add(env, "g_math", "math", by=head)
    with pytest.raises(ValidationError, match="Guruh bu vaqtda"):
        add(env, "g_it", "it", by=head)
    other = SchoolClass.objects.create(branch=branch, academic_year=year, name="5-A", grade=5)
    g_other = Group.objects.create(branch=branch, academic_year=year, school_class=other, code="IT-5A")
    GroupSubject.objects.create(group=g_other, subject=env["it"], teacher=env["t1"])
    env["g_other"] = g_other
    with pytest.raises(ValidationError, match="O'qituvchi Birinchi T bu vaqtda band"):
        add(env, "g_other", "it", by=head)
    GroupSubject.objects.filter(group=g_other).update(teacher=env["t2"])
    with pytest.raises(ValidationError, match="xonasi bu vaqtda band"):
        add(env, "g_other", "it", room=env["room"], by=head)
    add(env, "g_other", "it", by=head)  # boshqa sinf, boshqa o'qituvchi, boshqa xona — mumkin
    # O'quvchi kesishuvi: 4-A o'quvchisi 5-A dagi tanlov guruhida
    s = Student.objects.create(branch=branch, last_name="T", first_name="S", birth_date=date(2016, 1, 1), gender="M",
                               grade=4, joined_at=MON, school_class=school_class)
    sub = Group.objects.create(branch=branch, academic_year=year, school_class=other, code="IT-SUB", kind="subset")
    GroupSubject.objects.create(group=sub, subject=env["math"], teacher=env["t2"])
    GroupMembership.objects.create(group=sub, student=s, joined_at=MON)
    env["sub"] = sub
    with pytest.raises(ValidationError, match="bir vaqtda ikki guruhda"):
        add(env, "sub", "math", weekday=1, slot=0, by=head)


def test_history_is_preserved(env, head):
    lesson = add(env, "g_it", "it", by=head)
    nxt = MON + timedelta(days=14)
    assert timetable.remove_lesson(lesson, on=nxt, by=head) == "closed"
    lesson.refresh_from_db()
    assert lesson.valid_to == nxt - timedelta(days=1)
    # Yopilgandan keyin shu katakka boshqa dars qo'yish mumkin (davrlar kesishmaydi)
    add(env, "g_math", "math", on=nxt, by=head)
    grid_old = selectors.timetable_grid(lesson.branch, week=MON, school_class=lesson.group.school_class_id)
    grid_new = selectors.timetable_grid(lesson.branch, week=nxt, school_class=lesson.group.school_class_id)
    assert grid_old["rows"][0]["cells"][0]["lessons"][0].subject.name == "IT"
    assert grid_new["rows"][0]["cells"][0]["lessons"][0].subject.name == "Matematika"
    # Hali boshlanmagan dars olib tashlansa — butunlay o'chadi
    future = add(env, "g_it", "it", weekday=2, on=nxt, by=head)
    assert timetable.remove_lesson(future, on=nxt, by=head) == "deleted" and not Lesson.objects.filter(pk=future.pk)


def test_lesson_count_for_payroll(env, head):
    lesson = add(env, "g_it", "it", by=head)            # dushanba, 07.09 dan
    add(env, "g_it", "it", weekday=3, slot=1, by=head)  # chorshanba
    sept = Lesson.objects.filter(teacher=env["t1"])
    assert selectors.lesson_count(sept, date(2026, 9, 1), date(2026, 9, 30)) == 4 + 4  # 7,14,21,28 · 9,16,23,30
    timetable.remove_lesson(lesson, on=date(2026, 9, 21), by=head)  # 21-dan dushanba darsi yo'q
    assert selectors.lesson_count(sept, date(2026, 9, 1), date(2026, 9, 30)) == 2 + 4


def test_teacher_change_in_group_splits_lessons(env, head, monkeypatch):
    from apps.academics.services import groups as group_service
    lesson = add(env, "g_it", "it", by=head)
    monkeypatch.setattr("apps.academics.services.groups.date", type("D", (), {"today": staticmethod(
        lambda: date(2026, 10, 5))}))
    g = env["g_it"]
    group_service.save_group(g, branch=g.branch, by=head, subjects=[group_service.SubjectTeacher(env["it"], env["t2"])],
                             school_class=g.school_class, code=g.code, kind=g.kind, level="", pay_scheme=g.pay_scheme,
                             rate=g.rate, deduction_percent=0, room=None, capacity=30, is_active=True)
    lesson.refresh_from_db()
    new = Lesson.objects.exclude(pk=lesson.pk).get()
    assert lesson.teacher == env["t1"] and lesson.valid_to == date(2026, 10, 4)
    assert new.teacher == env["t2"] and new.valid_from == date(2026, 10, 5)
    with pytest.raises(ValidationError, match="darslari bor"):  # darsi bor fanni guruhdan olib bo'lmaydi
        group_service.save_group(g, branch=g.branch, by=head,
                                 subjects=[group_service.SubjectTeacher(env["math"], env["t2"])],
                                 school_class=g.school_class, code=g.code, kind=g.kind, level="",
                                 pay_scheme=g.pay_scheme, rate=g.rate, deduction_percent=0, room=None, capacity=30,
                                 is_active=True)


def test_bells_validation(branch, head):
    timetable.ensure_slots(branch)
    rows = [timetable.SlotRow(1, time(8, 30), time(9, 20)), timetable.SlotRow(2, time(9, 10), time(10, 0))]
    with pytest.raises(ValidationError, match="tugashidan oldin"):
        timetable.save_slots(branch, rows, by=head)
    timetable.save_slots(branch, [timetable.SlotRow(1, time(8, 0), time(8, 45))], by=head)
    assert list(TimeSlot.objects.filter(branch=branch).values_list("number", flat=True)) == [1]


def test_timetable_pages(head_client, env, school_class):
    url = reverse("academics:timetable")
    assert "grid" not in head_client.get(url).context  # sinf tanlanmagan — bo'sh holat
    resp = head_client.post(reverse("academics:lesson_create"), {
        "weekday": 1, "slot": env["slots"][0].pk, "group": env["g_it"].pk, "subject": env["it"].pk,
        "on": "2026-09-07", "next": url})
    assert resp.status_code == 302 and Lesson.objects.count() == 1
    resp = head_client.get(url, {"school_class": school_class.pk, "week": "2026-09-09"})
    assert resp.context["grid"]["total"] == 1 and resp.context["grid"]["monday"] == MON
    panel = head_client.get(reverse("academics:lesson_panel_new"), {"class": school_class.pk,
                                                                    "slot": env["slots"][1].pk, "weekday": 2})
    assert panel.status_code == 200 and len(panel.context["subject_map"]) == 2
    assert head_client.get(reverse("academics:timetable_print"), {"school_class": school_class.pk}).status_code == 200
    assert head_client.get(url, {"by": "teacher", "teacher": env["t1"].pk, "week": "2026-09-07"}) \
        .context["grid"]["total"] == 1


def test_timetable_only_head_teacher(staff_client):
    assert staff_client.get(reverse("academics:timetable")).status_code in (302, 403)


def test_default_start_date(head_client, env, school_class, head, year):
    params = {"class": school_class.pk, "slot": env["slots"][0].pk, "weekday": 1, "week": "2026-10-01"}
    url = reverse("academics:lesson_panel_new")
    # Sinf jadvali bo'sh — o'quv yili boshidan (o'tgan oylar ham hisoblansin)
    assert head_client.get(url, params).context["form"].initial["on"] == year.start_date
    add(env, "g_it", "it", by=head)
    # Jadvalda dars bor — ko'rsatilgan haftaning dushanbasidan
    assert head_client.get(url, params).context["form"].initial["on"] == date(2026, 9, 28)


# ---------- Sudrab qo'yish: fan kartalari, hovuz, ko'chirish, obed ----------

@pytest.fixture
def pool(env, branch, year, school_class):
    """Ingliz tili — sinf ikki tanlov guruhiga bo'lingan (hovuz), har birida o'z o'qituvchisi."""
    eng = Subject.objects.create(name="Ingliz tili")
    t3 = teacher(branch, "998900000173", "Uchinchi")
    groups = []
    for code, t in (("ENG-4A-1", env["t1"]), ("ENG-4A-2", t3)):
        g = Group.objects.create(branch=branch, academic_year=year, school_class=school_class, code=code,
                                 kind="subset")
        GroupSubject.objects.create(group=g, subject=eng, teacher=t, hours_per_week=2)
        groups.append(g)
    GroupSubject.objects.filter(group=env["g_it"]).update(hours_per_week=1)
    return {"eng": eng, "groups": groups}


def test_subject_cards_pool_and_limits(env, pool, head, school_class, branch):
    cards = selectors.subject_cards(branch, school_class, week=MON)
    by_name = {c["subject"].name: c for c in cards["cards"]}
    eng = by_name["Ingliz tili"]
    assert eng["pool"] and len(eng["parts"]) == 2 and eng["hours"] == 2 and eng["placed"] == 0
    timetable.place_card(groups=pool["groups"], subject=pool["eng"], weekday=1, slot=env["slots"][0], on=MON, by=head)
    assert Lesson.objects.filter(subject=pool["eng"]).count() == 2  # hovuz — ikkala guruh bir vaqtda
    add(env, "g_it", "it", weekday=2, by=head)
    cards = selectors.subject_cards(branch, school_class, week=MON)
    by_name = {c["subject"].name: c for c in cards["cards"]}
    assert by_name["Ingliz tili"]["placed"] == 1 and by_name["IT"]["full"] and cards["placed"] == 2


def test_place_endpoint_is_atomic_and_reports_conflicts(head_client, env, pool, head):
    url = reverse("academics:lesson_place")
    ids = ",".join(str(g.pk) for g in pool["groups"])
    # IT-4A darsi (t1) dushanba 1-darsda — ENG-4A-1 ham t1 → ziddiyat; hovuzning hech biri qo'yilmasin
    add(env, "g_it", "it", by=head)
    resp = head_client.post(url, {"groups": ids, "subject": pool["eng"].pk, "weekday": 1,
                                  "slot": env["slots"][0].pk, "on": "2026-09-07"})
    assert resp.status_code == 400 and "ENG-4A-1" in resp.json()["errors"][0]
    assert not Lesson.objects.filter(subject=pool["eng"]).exists()
    resp = head_client.post(url, {"groups": ids, "subject": pool["eng"].pk, "weekday": 1,
                                  "slot": env["slots"][1].pk, "on": "2026-09-07"})
    assert resp.status_code == 200 and resp.json()["ok"]
    assert Lesson.objects.filter(subject=pool["eng"]).count() == 2


def test_move_lesson_keeps_history(head_client, env, head):
    lesson = add(env, "g_it", "it", by=head)
    resp = head_client.post(reverse("academics:lesson_move", args=[lesson.pk]),
                            {"weekday": 3, "slot": env["slots"][2].pk, "on": "2026-09-21"})
    assert resp.status_code == 200
    lesson.refresh_from_db()
    moved = Lesson.objects.exclude(pk=lesson.pk).get()
    assert lesson.valid_to == date(2026, 9, 20) and (moved.weekday, moved.valid_from) == (3, date(2026, 9, 21))
    # ziddiyatga ko'chirish — hech narsa o'zgarmaydi
    other = add(env, "g_math", "math", weekday=4, by=head)
    resp = head_client.post(reverse("academics:lesson_move", args=[other.pk]),
                            {"weekday": 3, "slot": env["slots"][2].pk, "on": "2026-09-21"})
    assert resp.status_code == 400 and Lesson.objects.filter(pk=other.pk, valid_to__isnull=True).exists()


def test_break_slot_rejects_lessons_and_renders(head_client, env, head, branch, school_class):
    slot = env["slots"][5]
    slot.is_break = True
    slot.save()
    with pytest.raises(ValidationError, match="tanaffus"):
        add(env, "g_it", "it", slot=5, by=head)
    html = head_client.get(reverse("academics:timetable"), {"school_class": school_class.pk}).content.decode()
    assert "OBED" in html and "data-drag-card" in html
    for name in ("academics:timetable_export", "academics:timetable_export_all"):
        assert head_client.get(reverse(name), {"school_class": school_class.pk}).status_code == 200
