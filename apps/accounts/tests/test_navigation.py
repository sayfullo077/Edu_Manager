import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.navigation import TAB_BAR, build_menu, build_tabbar


@pytest.mark.parametrize("role", list(TAB_BAR))
def test_tabbar_items_come_from_menu(role):
    """Tab bar bandlari rol menyusida bo'lishi shart — aks holda telefonda bo'lim yo'qolib qoladi."""
    tabs = build_tabbar(role, build_menu(role, reverse("core:home")))
    assert [t["short"] for t in tabs] == [short for _, short in TAB_BAR[role]]
    assert tabs[0]["active"] and not any(t["active"] for t in tabs[1:])  # bosh sahifada faqat "Asosiy"


def test_tabbar_marks_current_section(staff_client):
    tabs = build_tabbar(Role.RECEPTION, build_menu(Role.RECEPTION, reverse("finance:debtor_list")))
    assert [t["short"] for t in tabs if t["active"]] == ["Qarzdorlar"]
    html = staff_client.get(reverse("finance:debtor_list")).content.decode()
    assert 'class="tabbar"' in html and "Qarzdorlar" in html
