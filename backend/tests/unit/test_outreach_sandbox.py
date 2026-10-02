"""Sandbox allowlist: pure, offline. An empty list allows nobody (fail closed)."""

import pytest

from services.outreach_os.sandbox import is_allowed, parse_allowlist


def test_parse_accepts_commas_semicolons_spaces_and_newlines_and_dedupes():
    raw = " Founder@Plantiers.com, @plantiers.com;test.example\nfounder@plantiers.com  "
    assert parse_allowlist(raw) == ("founder@plantiers.com", "@plantiers.com", "test.example")
    assert parse_allowlist("") == parse_allowlist(None) == ()


@pytest.mark.parametrize(
    "recipient, allowlist, expected",
    [
        ("founder@plantiers.com", ("founder@plantiers.com",), True),
        ("FOUNDER@Plantiers.com", ("founder@plantiers.com",), True),
        ("other@plantiers.com", ("founder@plantiers.com",), False),  # a full address allows that address only
        ("other@plantiers.com", ("@plantiers.com",), True),
        ("other@plantiers.com", ("plantiers.com",), True),
        ("other@mail.plantiers.com", ("plantiers.com",), False),  # subdomains are not implied
        ("other@evilplantiers.com", ("plantiers.com",), False),
        ("other@plantiers.com.evil.example", ("plantiers.com",), False),
        ("anyone@x.example", (), False),  # empty allowlist: nobody
        ("not-an-address", ("plantiers.com",), False),
        ("", ("plantiers.com",), False),
    ],
)
def test_is_allowed(recipient, allowlist, expected):
    assert is_allowed(recipient, allowlist) is expected
