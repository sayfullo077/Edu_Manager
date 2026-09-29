from django.db import models, transaction


class CodeSequence(models.Model):
    """Inson o'qiy oladigan kodlar uchun ketma-ketlik: STD-2026-001, TCH-2026-009, CTR-2026-445.

    `select_for_update` bilan: bir vaqtda ikki admin o'quvchi qo'shsa ham kod takrorlanmaydi.
    """

    prefix = models.CharField(max_length=10)
    year = models.PositiveSmallIntegerField()
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["prefix", "year"], name="unique_code_sequence")]

    def __str__(self):
        return f"{self.prefix}-{self.year}: {self.last_value}"

    @classmethod
    def next_code(cls, prefix: str, year: int, width: int = 3) -> str:
        with transaction.atomic():
            seq, _ = cls.objects.select_for_update().get_or_create(prefix=prefix, year=year)
            seq.last_value += 1
            seq.save(update_fields=["last_value"])
        return f"{prefix}-{year}-{seq.last_value:0{width}d}"
