"""O'qituvchi oyligi — sof hisob (Django'siz). Formulalar: docs/PLAN.md 3-bo'lim.

Har bir o'quvchi ulushi:  real = to'langan / to'liq_tarif,  max = to'lanishi_kerak / to'liq_tarif.
  Darsbay:     dars_soni × stavka × ulush
  O'quvchibay: stavka × ulush, keyin ushlanma (%) — «Jarimalar» ustuniga
Ustamalar (foydalanuvchi qarori, 2026-10-02):
  Toifa      — toifa foizi × darsbay qismi
  Sertifikat — foiz × amaldagi sertifikat fanidan tushgan qism (fani ko'rsatilmagan sertifikat — barcha fanlar)
  Til        — foiz × ta'lim tili o'zbekcha bo'lmagan sinflar qismi
  S/R        — o'quvchi boshiga stavka × ulush (sinfning har bir o'quvchisi; asl jadvaldan, 2026-10-02)
Real oylik = Asosiy (+ belgilangan oylik) + ustamalar + S/R − jarimalar (ushlanma + qo'lda jarima).
Qator (guruh fani) summasi = asosiy + shu qatorga tegishli ustamalar − ushlanma (asl sahifadagidek).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

ZERO = Decimal("0")
HUNDRED = Decimal("100")
CENT = Decimal("0.01")


@dataclass(frozen=True)
class Pair:
    """Bir vaqtda ikki qiymat: haqiqatda (to'langan bo'yicha) va 100% (hammasi to'lasa)."""

    real: Decimal = ZERO
    max: Decimal = ZERO

    def __add__(self, other: Pair) -> Pair:
        return Pair(self.real + other.real, self.max + other.max)

    def __sub__(self, other: Pair) -> Pair:
        return Pair(self.real - other.real, self.max - other.max)

    def pct(self, percent: Decimal) -> Pair:
        return Pair(self.real * percent / HUNDRED, self.max * percent / HUNDRED)

    def rounded(self) -> Pair:
        return Pair(self.real.quantize(CENT), self.max.quantize(CENT))

    def __bool__(self) -> bool:
        return bool(self.real or self.max)


@dataclass(frozen=True)
class StudentShare:
    student_id: int
    name: str
    paid: Decimal
    amount: Decimal
    full: Decimal

    @property
    def ratio(self) -> Pair:
        if not self.full:
            return Pair()
        return Pair(self.paid / self.full, self.amount / self.full)


@dataclass
class Line:
    """O'qituvchining bitta guruh fani bo'yicha oylik qismi."""

    group_id: int
    group_code: str
    class_name: str
    subject_id: int
    subject_name: str
    per_lesson: bool
    rate: Decimal
    deduction_percent: Decimal
    lessons: int
    foreign: bool  # sinf ta'lim tili o'zbekcha emas
    students: list[StudentShare] = field(default_factory=list)

    def student_amount(self, s: StudentShare) -> Pair:
        r = s.ratio
        k = self.rate * self.lessons if self.per_lesson else self.rate
        return Pair(r.real * k, r.max * k)

    @property
    def rows(self) -> list[tuple[StudentShare, Pair]]:
        return [(s, self.student_amount(s)) for s in self.students]

    @property
    def gross(self) -> Pair:
        total = Pair()
        for s in self.students:
            total += self.student_amount(s)
        return total

    @property
    def deduction(self) -> Pair:
        if self.per_lesson or not self.deduction_percent:
            return Pair()
        return self.gross.pct(self.deduction_percent)


@dataclass
class Homeroom:
    """Sinf rahbarligi: sinfning shu oy to'lov grafigi bor o'quvchilari."""

    class_name: str
    students: list[StudentShare] = field(default_factory=list)

    def amount(self, rate: Decimal) -> Pair:
        total = Pair()
        for s in self.students:
            r = s.ratio
            total += Pair(r.real * rate, r.max * rate)
        return total


@dataclass(frozen=True)
class Rates:
    category_percent: Decimal = ZERO
    certificate_percent: Decimal = ZERO
    language_percent: Decimal = ZERO
    homeroom_rate: Decimal = ZERO  # o'quvchi boshiga


@dataclass
class TeacherPay:
    teacher_id: int
    rates: Rates
    lines: list[Line] = field(default_factory=list)
    fixed_salary: Decimal = ZERO
    cert_subjects: frozenset[int] = frozenset()
    cert_all_subjects: bool = False  # fani ko'rsatilmagan amaldagi sertifikat bor
    homerooms: list[Homeroom] = field(default_factory=list)
    penalties: Decimal = ZERO

    # --- ko'rsatkichlar ---
    @property
    def subjects_count(self) -> int:
        return len(self.lines)

    @property
    def lessons(self) -> int:
        return sum(line.lessons for line in self.lines)

    @property
    def students_count(self) -> int:
        return len({s.student_id for line in self.lines for s in line.students})

    # --- qator bo'yicha ustamalar ---
    def has_certificate(self, line: Line) -> bool:
        return self.cert_all_subjects or line.subject_id in self.cert_subjects

    def line_category(self, line: Line) -> Pair:
        return line.gross.pct(self.rates.category_percent) if line.per_lesson else Pair()

    def line_certificate(self, line: Line) -> Pair:
        return line.gross.pct(self.rates.certificate_percent) if self.has_certificate(line) else Pair()

    def line_language(self, line: Line) -> Pair:
        return line.gross.pct(self.rates.language_percent) if line.foreign else Pair()

    def line_bonus(self, line: Line) -> Pair:
        return self.line_category(line) + self.line_certificate(line) + self.line_language(line)

    @property
    def items(self) -> list[dict]:
        """Sahifa uchun: har qator — asosiy, ustama, ushlanma va jami (asl sahifadagi «Shartnomalar» ro'yxati)."""
        result = []
        for line in self.lines:
            bonus, deduction = self.line_bonus(line), line.deduction
            result.append({"line": line, "bonus": bonus, "deduction": deduction,
                           "total": line.gross + bonus - deduction})
        return result

    @property
    def homeroom_items(self) -> list[dict]:
        return [{"homeroom": h, "total": h.amount(self.rates.homeroom_rate)} for h in self.homerooms]

    # --- summalar ---
    def _sum(self, fn) -> Pair:
        total = Pair()
        for line in self.lines:
            total += fn(line)
        return total

    @property
    def base(self) -> Pair:
        return self._sum(lambda x: x.gross) + Pair(self.fixed_salary, self.fixed_salary)

    @property
    def category_bonus(self) -> Pair:
        return self._sum(self.line_category)

    @property
    def certificate_bonus(self) -> Pair:
        return self._sum(self.line_certificate)

    @property
    def language_bonus(self) -> Pair:
        return self._sum(self.line_language)

    @property
    def bonuses(self) -> Pair:
        return self.category_bonus + self.certificate_bonus + self.language_bonus

    @property
    def homeroom_bonus(self) -> Pair:
        total = Pair()
        for h in self.homerooms:
            total += h.amount(self.rates.homeroom_rate)
        return total

    @property
    def homeroom_students(self) -> int:
        return sum(len(h.students) for h in self.homerooms)

    @property
    def deductions(self) -> Pair:
        total = Pair(self.penalties, self.penalties)
        for line in self.lines:
            total += line.deduction
        return total

    @property
    def total(self) -> Pair:
        return self.base + self.bonuses + self.homeroom_bonus - self.deductions

    @property
    def gap(self) -> Decimal:
        """Farq: to'lanmagan pul sababli 100% dan kam hisoblangan qism (manfiy)."""
        return self.total.real - self.total.max

    @property
    def is_empty(self) -> bool:
        return not (self.lines or self.fixed_salary or self.homerooms or self.penalties)
