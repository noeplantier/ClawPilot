"""Which provider sends, and the known B2B relays: read-only, names of variables only, never a secret."""

import requests

from tests.test_map_quick_add import API, _org


def test_the_providers_are_listed_without_any_secret():
    _, h, _ = _org()
    r = requests.get(f"{API}/email-providers", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["server_variables"] == ["SMTP_HOST", "SMTP_PORT", "SMTP_SECURITY", "SMTP_USERNAME", "SMTP_PASSWORD"]
    assert {p["id"] for p in body["relays"]} >= {
        "brevo",
        "mailjet",
        "sendgrid",
        "mailgun",
        "google",
        "microsoft",
        "zoho",
    }
    assert sum(p["recommended"] for p in body["relays"]) == 1
    assert body["current"]["id"] == "none" and body["smtp_configured"] is False  # the test server has no provider
    assert "password" not in r.text.lower().replace("smtp_password", "")


def test_an_anonymous_request_is_refused():
    assert requests.get(f"{API}/email-providers").status_code in (401, 403)
