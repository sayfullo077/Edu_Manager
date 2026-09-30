"""Yotoqxona demo ma'lumotlari: 3 ta xona va jinsiga mos joylashtirilgan faol o'quvchilar. Takrorlanmaydi."""

from datetime import date
from decimal import Decimal

from apps.finance.services import payments
from apps.people.models import Student

from .models import DormRoom, DormStay
from .services import stays

ROOMS = [  # (nomi, qavat, turi, jinsi, sig'im, oylik to'lov)
    ("1-xona bog'cha", "", 2, DormRoom.Gender.MALE, 40, Decimal("600000")),
    ("29-xona", "1-qavat", 8, DormRoom.Gender.FEMALE, 30, Decimal("600000")),
    ("30-xona", "1-qavat", 8, DormRoom.Gender.FEMALE, 30, Decimal("600000")),
]


def seed(branch, reception_user) -> dict:
    rooms = []
    for name, floor, room_type, gender, capacity, fee in ROOMS:
        room, _ = DormRoom.objects.get_or_create(branch=branch, name=name, defaults={
            "floor": floor, "room_type": room_type, "gender": gender, "capacity": capacity, "monthly_fee": fee})
        rooms.append(room)
    if DormStay.objects.filter(room__branch=branch).exists():
        return {"rooms": len(rooms), "stays": 0}
    created = 0
    active = Student.objects.filter(branch=branch, status=Student.Status.ACTIVE).order_by("code")
    boys, girls = [s for s in active if s.gender == "M"][:14], [s for s in active if s.gender == "F"][:8]
    for student, room in [(s, rooms[0]) for s in boys] + [(s, rooms[1 + i % 2]) for i, s in enumerate(girls)]:
        stay = stays.check_in(student=student, room=room, on=date(2026, 9, 16), by=reception_user)
        created += 1
        if created % 3:  # har uchinchidan boshqasi qisman yoki to'liq to'lagan
            inv = stay.invoices.first()
            if inv:
                payments.accept_payment(student=student, amount=inv.amount if created % 2 else inv.amount / 2,
                                        method="transfer", category="dorm", by=reception_user)
    return {"rooms": len(rooms), "stays": created}
