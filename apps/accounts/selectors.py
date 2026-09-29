"""O'qish so'rovlari (query). Biznes logika yo'q — faqat ma'lumot olish, optimallashtirilgan holda."""

from .models import ROLE_ORDER, TelegramLink, User, UserRole


def active_user_by_phone(phone: str) -> User | None:
    return User.objects.filter(phone=phone, is_active=True).first()


def available_roles(user: User, branch=None) -> list[UserRole]:
    qs = (UserRole.objects
          .filter(user=user, is_active=True, branch__is_active=True)
          .select_related("branch"))
    if branch is not None:
        qs = qs.filter(branch=branch)
    return sorted(qs, key=lambda r: (r.branch.name, ROLE_ORDER.get(r.role, 99)))


def telegram_chat_id(user: User) -> int | None:
    return TelegramLink.objects.filter(user=user).values_list("chat_id", flat=True).first()
