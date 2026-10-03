"""Demo ma'lumotlar: sinflar, fanlar, guruhlar, o'quvchilar va ota-onalar.

Barcha ism, telefon, passport va JSHSHIR'lar TASODIFIY va SOXTA — haqiqiy odamlarga tegishli emas.
Qayta ishga tushirilsa takrorlanmaydi (idempotent).
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from apps.academics.models import Group, GroupMembership, GroupSubject, Language, Room, SchoolClass, Subject

from .models import Guardian, Student, StudentGuardian, Teacher

MALE = ["Aziz", "Bekzod", "Jasur", "Sardor", "Otabek", "Diyor", "Javohir", "Abdulloh", "Islom", "Muhammad",
        "Sanjar", "Temur", "Asilbek", "Ibrohim", "Umar", "Yusuf", "Shohruh", "Behruz", "Firdavs", "Nurbek"]
FEMALE = ["Madina", "Sevinch", "Zarina", "Mohinur", "Dilnoza", "Shahzoda", "Nigora", "Sabina", "Oysha",
          "Maftuna", "Gulnoza", "Rayhona", "Mubina", "Zilola", "Fotima", "Shirin", "Laylo", "Kamola"]
SURNAMES = ["Karimov", "Rahimov", "Tursunov", "Yusupov", "Aliyev", "Sobirov", "Qodirov", "Nazarov", "Ergashev",
            "Hamidov", "Toshpulatov", "Mirzayev", "Olimov", "Salimov", "Jo'rayev", "Normatov", "Xolmatov"]
FATHERS = ["Anvar", "Bahodir", "Dilshod", "Farrux", "Ilhom", "Jamshid", "Rustam", "Shavkat", "Ulug'bek", "Zafar"]

CLASSES = [  # (nomi, turi, daraja, tili)
    ("1-D", "regular", 1, "ru"), ("2-B", "regular", 2, "uz"), ("3-B", "regular", 3, "uz"),
    ("3-C", "regular", 3, "ru"), ("4-A", "regular", 4, "uz"), ("4-B", "regular", 4, "ru"),
    ("5-A", "regular", 5, "uz"), ("5-B", "regular", 5, "uz"), ("6-A", "regular", 6, "uz"),
    ("Aniq1", "direction", None, "uz"), ("Aniq2", "direction", None, "uz"), ("Ijtimoiy1", "direction", None, "uz"),
]
SUBJECTS = [("IT (Kompyuter savodxonligi)", "uz"), ("IT (Компьютерная грамотность)", "ru"),
            ("IT (Dasturlash)", "uz"), ("Fizika", "uz"), ("Matematika", "uz"), ("Ingliz tili", "uz")]


def _surname(rng, female):
    s = rng.choice(SURNAMES)
    return s + "a" if female and s.endswith(("ov", "ev")) else s


def _student_name(rng, female):
    first = rng.choice(FEMALE if female else MALE)
    father = rng.choice(FATHERS)
    return _surname(rng, female), first, f"{father} {'qizi' if female else "o'g'li"}"


def seed(branch, year, teacher_users, students_per_class=6) -> dict:
    rng = random.Random(2026)  # noqa: S311 — kriptografiya emas, faqat demo ma'lumot

    subjects = {name: Subject.objects.get_or_create(name=name, language=lang)[0] for name, lang in SUBJECTS}
    room, _ = Room.objects.get_or_create(branch=branch, name="31-xona", defaults={"capacity": 30})

    teachers = []
    for i, user in enumerate(teacher_users):
        t, _ = Teacher.objects.get_or_create(user=user, defaults={
            "branch": branch, "gender": "M", "education": Teacher.Education.HIGHER, "experience_years": 3 + i,
            "hired_at": date(2026, 9, 2), "contract_start": date(2026, 9, 2), "contract_end": date(2027, 8, 27),
            "teaching_languages": [Language.UZ]})
        t.subjects.add(subjects["IT (Kompyuter savodxonligi)"], subjects["IT (Dasturlash)"])
        teachers.append(t)

    classes = {}
    for name, kind, grade, lang in CLASSES:
        classes[name], _ = SchoolClass.objects.get_or_create(
            branch=branch, academic_year=year, name=name,
            defaults={"kind": kind, "grade": grade, "language": lang, "room": room,
                      "monthly_tariff": Decimal("1850000") if lang == "ru" else Decimal("1750000")})

    if not Student.objects.filter(branch=branch).exists():
        for sc in classes.values():
            for _ in range(students_per_class):
                female = rng.random() < 0.45
                last, first, middle = _student_name(rng, female)
                grade = sc.grade or rng.choice([7, 8, 9])
                born = date(2026 - grade - 6, 1, 1) + timedelta(days=rng.randrange(365))
                # Faqat ketgan sana (left_at) talab qilmaydigan holatlar — ketganlar demo'da yaratilmaydi
                status = rng.choices([Student.Status.ACTIVE, Student.Status.FROZEN, Student.Status.INACTIVE],
                                     weights=[92, 5, 3])[0]
                student = Student.objects.create(
                    branch=branch, last_name=last, first_name=first, middle_name=middle, birth_date=born,
                    gender="F" if female else "M", phone=f"99890{rng.randrange(10**7):07d}", grade=grade,
                    school_class=sc, status=status, joined_at=date(2026, 9, rng.choice([2, 2, 2, 15])),
                    in_erp=rng.random() < 0.6, in_emaktab=rng.random() < 0.4)
                g_last = student.last_name[:-1] if female and student.last_name.endswith("a") else student.last_name
                guardian = Guardian.objects.create(
                    last_name=g_last, first_name=middle.split()[0], phone=f"99891{rng.randrange(10**7):07d}",
                    passport=f"A{rng.choice('BCD')}{rng.randrange(10**7):07d}",
                    pinfl=f"{rng.choice([3, 4])}{rng.randrange(10**13):013d}")
                StudentGuardian.objects.create(student=student, guardian=guardian,
                                               relation=StudentGuardian.Relation.FATHER, is_primary=True)

    if teachers:
        for cname in ("3-B", "4-A", "5-A", "6-A"):
            g, created = Group.objects.get_or_create(
                branch=branch, academic_year=year, code=f"IT-{cname}",
                defaults={"school_class": classes[cname], "kind": Group.Kind.WHOLE_CLASS,
                          "pay_scheme": Group.PayScheme.PER_LESSON, "rate": Decimal("2400"), "room": room})
            if created:
                GroupSubject.objects.create(group=g, subject=subjects["IT (Kompyuter savodxonligi)"],
                                            teacher=teachers[0])
        for cname in ("Aniq1", "Aniq2"):
            g, created = Group.objects.get_or_create(
                branch=branch, academic_year=year, code=f"IT+PHYS-{cname}-01",
                defaults={"school_class": classes[cname], "kind": Group.Kind.SUBSET, "level": "2-darajali fanlarga",
                          "pay_scheme": Group.PayScheme.PER_STUDENT, "rate": Decimal("120000"),
                          "deduction_percent": Decimal("15"), "room": room})
            if created:
                GroupSubject.objects.create(group=g, subject=subjects["IT (Dasturlash)"], teacher=teachers[0])
                for s in classes[cname].students.filter(status=Student.Status.ACTIVE):
                    GroupMembership.objects.create(group=g, student=s, joined_at=s.joined_at)

    return {"classes": len(classes), "students": Student.objects.filter(branch=branch).count()}
