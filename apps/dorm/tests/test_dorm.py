from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.dorm import selectors
from apps.dorm.models import DormRoom, DormStay
from apps.dorm.services import stays
from apps.people.models import Student


def make_student(branch, name, gender="M", **kw):
    return Student.objects.create(branch=branch, last_name="Test", first_name=name, birth_date=date(2014, 1, 1),
                                  gender=gender, grade=6, joined_at=date(2026, 9, 2), **kw)


@pytest.fixture
def rooms(branch):
    return (DormRoom.objects.create(branch=branch, name="1-xona", gender="male", capacity=2),
            DormRoom.objects.create(branch=branch, name="2-xona", gender="female", capacity=3))


def test_check_in_rules(branch, other_branch, rooms, reception):
    boys, girls = rooms
    a, b, c = (make_student(branch, n) for n in ("Ali", "Bobur", "Davron"))
    stays.check_in(student=a, room=boys, on=date(2026, 9, 16), by=reception)
    stays.check_in(student=b, room=boys, on=date(2026, 9, 16), by=reception)
    with pytest.raises(ValidationError):  # o'rin qolmadi
        stays.check_in(student=c, room=boys, on=date(2026, 9, 16), by=reception)
    with pytest.raises(ValidationError):  # qizlar xonasi
        stays.check_in(student=c, room=girls, on=date(2026, 9, 16), by=reception)
    with pytest.raises(ValidationError):  # allaqachon yashayapti
        stays.check_in(student=a, room=boys, on=date(2026, 9, 17), by=reception)
    with pytest.raises(ValidationError):  # faol emas
        stays.check_in(student=make_student(branch, "Eski", "F", status="left"), room=girls, on=date(2026, 9, 16),
                       by=reception)
    with pytest.raises(ValidationError):  # boshqa filial
        stays.check_in(student=make_student(other_branch, "Boshqa", "F"), room=girls, on=date(2026, 9, 16),
                       by=reception)
    stay = DormStay.objects.get(student=a)
    stays.check_out(stay, on=date(2026, 10, 1), by=reception)
    stays.check_in(student=c, room=boys, on=date(2026, 10, 1), by=reception)  # o'rin bo'shadi
    assert DormStay.objects.filter(student=a).count() == 1  # tarix saqlanadi


def test_occupancy_and_dashboard(staff_client, branch, rooms, reception):
    boys, girls = rooms
    stays.check_in(student=make_student(branch, "Ali"), room=boys, on=date(2026, 9, 16), by=reception)
    for i in range(3):
        stays.check_in(student=make_student(branch, f"Qiz{i}", "F"), room=girls, on=date(2026, 9, 20 + i),
                       by=reception)
    o = selectors.occupancy(branch)
    assert (o["rooms"], o["capacity"], o["occupied"], o["free"], o["percent"]) == (2, 5, 4, 1, 80)
    assert (o["male"], o["female"], o["mixed"]) == (1, 1, 0)
    url = reverse("dorm:dashboard")
    resp = staff_client.get(url)
    assert resp.context["total"] == 4 and resp.context["shown"] == 4
    assert staff_client.get(url, {"gender": "F"}).context["total"] == 3
    assert staff_client.get(url, {"room": boys.pk}).context["total"] == 1
    assert staff_client.get(url, {"date_from": "2026-09-21"}).context["total"] == 2
    assert staff_client.get(reverse("dorm:residents_export")).status_code == 200


def test_load_more_step(staff_client, branch, reception):
    room = DormRoom.objects.create(branch=branch, name="Katta", gender="mixed", capacity=50)
    for i in range(25):
        stays.check_in(student=make_student(branch, f"S{i:02d}"), room=room, on=date(2026, 9, 16), by=reception)
    resp = staff_client.get(reverse("dorm:dashboard"))
    assert (resp.context["shown"], resp.context["total"]) == (20, 25) and "limit=40" in resp.context["more_query"]
    assert staff_client.get(reverse("dorm:dashboard"), {"limit": "40"}).context["shown"] == 25


def test_dorm_reception_only(client, teacher_user):
    client.force_login(teacher_user)
    assert client.get(reverse("dorm:dashboard")).status_code in (302, 403)


def test_room_list_filters_and_stats(staff_client, branch, rooms):
    DormRoom.objects.create(branch=branch, name="30-xona", floor="1-qavat", room_type=8, gender="female",
                            capacity=20, status="repair")
    url = reverse("dorm:room_list")
    resp = staff_client.get(url)
    assert resp.context["stats"] == {"total": 3, "active": 2, "inactive": 0, "repair": 1}
    assert [r.name for r in staff_client.get(url, {"status": "repair"}).context["rooms"]] == ["30-xona"]
    assert len(staff_client.get(url, {"gender": "female"}).context["rooms"]) == 2
    assert [r.name for r in staff_client.get(url, {"room_type": "8"}).context["rooms"]] == ["30-xona"]
    assert [r.name for r in staff_client.get(url, {"q": "2-x"}).context["rooms"]] == ["2-xona"]
    assert staff_client.get(reverse("dorm:room_export")).status_code == 200


def test_room_detail_check_in_and_out(staff_client, branch, rooms, reception):
    boys, _ = rooms
    ali, qiz = make_student(branch, "Ali"), make_student(branch, "Malika", "F")
    url = reverse("dorm:room_detail", args=[boys.pk])
    candidates = list(staff_client.get(url).context["form"].fields["student"].queryset)
    assert ali in candidates and qiz not in candidates  # jinsi mos emas
    resp = staff_client.post(url, {"student": ali.pk, "on": "2026-09-20", "note": "1-karavot"})
    assert resp.status_code == 302 and DormStay.objects.get(student=ali).note == "1-karavot"
    assert ali not in staff_client.get(url).context["form"].fields["student"].queryset  # endi yashayapti
    stay = DormStay.objects.get(student=ali)
    staff_client.post(reverse("dorm:stay_check_out", args=[stay.pk]), {"on": "2026-09-25"})
    stay.refresh_from_db()
    assert stay.checked_out == date(2026, 9, 25)


def test_repair_room_rejects_check_in(branch, rooms, reception):
    boys, _ = rooms
    boys.status = DormRoom.Status.REPAIR
    boys.save()
    with pytest.raises(ValidationError):
        stays.check_in(student=make_student(branch, "Ali"), room=boys, on=date(2026, 9, 16), by=reception)


def test_only_most_specific_nav_item_is_active():
    from apps.accounts.models import Role
    from apps.accounts.navigation import build_menu

    def active(path):
        return [e["item"].label for g in build_menu(Role.RECEPTION, path) for e in g["items"] if e["active"]]

    assert active(reverse("dorm:room_list")) == ["Xonalar"]
    assert active(reverse("dorm:room_detail", args=[1])) == ["Xonalar"]
    assert active(reverse("dorm:dashboard")) == ["Boshqaruv paneli"]
    assert active(reverse("people:student_list")) == ["O'quvchilar"]
