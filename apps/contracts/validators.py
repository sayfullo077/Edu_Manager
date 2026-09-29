from django.core.exceptions import ValidationError

MAX_SCAN_BYTES = 5 * 1024 * 1024


def validate_pdf(file) -> None:
    """Kengaytma yetarli emas: fayl haqiqatan PDF ekanini (magic bytes) va hajmini tekshiramiz."""
    if file.size > MAX_SCAN_BYTES:
        raise ValidationError("Fayl hajmi 5 MB dan oshmasligi kerak.")
    pos = file.tell() if hasattr(file, "tell") else 0
    file.seek(0)
    header = file.read(5)
    file.seek(pos)
    if header != b"%PDF-":
        raise ValidationError("Faqat PDF fayl yuklash mumkin.")
