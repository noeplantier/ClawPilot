"""Which provider sends, and the known B2B relays: read-only, names of variables only, never a secret."""

import requests

from tests.test_map_quick_add import API, _org


def test_the_providers_are_listed_without_any_secret():
    _, h, _ = _org()
    r = requests.get(f"{API}/email-providers", headers=h)
    assert r.status_code == 200
    body = r.json()
    smtp = ["SMTP_HOST", "SMTP_PORT", "SMTP_SECURITY", "SMTP_USERNAME", "SMTP_PASSWORD"]
    assert body["smtp_variables"] == smtp
    assert body["server_variables"] == ["RESEND_API_KEY", "BREVO_API_KEY", *smtp]
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
    assert body["order"] == ["resend", "brevo", "smtp"]  # the order mail_provider.live_adapter tries them in
    channels = {c["id"]: c for c in body["api_channels"]}
    assert [c["id"] for c in body["api_channels"]] == ["resend", "brevo"]
    assert channels["resend"]["variable"] == "RESEND_API_KEY" and channels["resend"]["recommended"] is True
    assert not any(c["configured"] or c["active"] for c in body["api_channels"])  # no key on the test server
    assert body["current"]["is_api"] is False
    assert "RESEND_API_KEY" in body["current"]["restriction"] and "SENDGRID" not in body["current"]["restriction"]


def test_the_api_channel_in_use_is_marked_active_and_its_key_never_shown(monkeypatch):
    import secrets

    from routes import email_providers
    from tasks._bridge import run_async

    key = "re_" + secrets.token_hex(12)  # generated per run: never a literal credential
    monkeypatch.setenv("RESEND_API_KEY", key)
    body = run_async(lambda session: email_providers.providers(user={}))
    assert body["current"]["id"] == "resend_api" and body["current"]["is_api"] is True
    resend, brevo = body["api_channels"]
    assert (resend["configured"], resend["active"]) == (True, True)
    assert (brevo["configured"], brevo["active"]) == (False, False)
    assert key not in repr(body)


def test_an_anonymous_request_is_refused():
    assert requests.get(f"{API}/email-providers").status_code in (401, 403)
