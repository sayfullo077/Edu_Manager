"""O'qish so'rovlari (query). Biznes logika yo'q — faqat ma'lumot olish, optimallashtirilgan holda."""

from .models import TelegramLink, User, UserRole


def active_user_by_phone(phone: str) -> User | None:
    return User.objects.filter(phone=phone, is_active=True).first()


def available_roles(user: User, branch=None) -> list[UserRole]:
    qs = (UserRole.objects
          .filter(user=user, is_active=True, branch__is_active=True)
          .select_related("branch")
          .order_by("branch__name", "role"))
    if branch is not None:
        qs = qs.filter(branch=branch)
    return list(qs)


def telegram_chat_id(user: User) -> int | None:
    return TelegramLink.objects.filter(user=user).values_list("chat_id", flat=True).first()
