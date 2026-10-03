"""Xavfsizlik auditi (2026-10-03) topilmalari qaytmasligi uchun."""

import pytest
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.models import Role
from apps.common.http import int_param, safe_next
from conftest import make_staff


@pytest.mark.parametrize("candidate,expected", [
    ("/students/?page=2", "/students/?page=2"),
    ("abc", "/fallback/"),                      # nisbiy — redirect() view nomi deb izlab 500 berardi
    ("//evil.com/x", "/fallback/"),             # boshqa sayt
    ("https://evil.com/", "/fallback/"),
    ("javascript:alert(1)", "/fallback/"),
    ("", "/fallback/"),
    (None, "/fallback/"),
])
def test_safe_next(candidate, expected):
    request = RequestFactory().get("/")
    assert safe_next(request, candidate, "/fallback/") == expected


@pytest.mark.parametrize("value,expected", [("5", 5), (" 7 ", 7), ("abc", None), ("1.5", None), (None, None),
                                            ("", None), ("0x10", None)])
def test_int_param(value, expected):
    assert int_param(value) == expected


@pytest.fixture
def head_client(client, branch):
    client.force_login(make_staff(branch, Role.HEAD_TEACHER, "998900000401"))
    return client


@pytest.mark.parametrize("url", [
    "/contracts/new/?student=abc", "/contracts/new/?student=1.5",
    "/timetable/lessons/new/?class=abc&slot=abc&weekday=abc", "/timetable/lessons/new/?class=&slot=&weekday=",
])
def test_garbage_get_params_do_not_crash(head_client, url):
    assert head_client.get(url).status_code < 500


@pytest.mark.parametrize("name", ["payroll:settings", "academics:bells"])
def test_garbage_next_does_not_crash(head_client, name):
    assert head_client.post(reverse(name), {"next": "abc"}).status_code < 500
