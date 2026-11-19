"""« Configured » is not « working »: the e-mail channel must be reachable from this server. A TCP probe only (no TLS,
no sign-in, nothing sent), cached. Offline: the connection is a recorder, no socket is opened."""

import secrets

import pytest

from services import mail_provider


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for name in ("OUTREACH_TEST_SINK", "BREVO_API_KEY", "RESEND_API_KEY", "SMTP_PORT", "SMTP_SECURITY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.hostinger.com")
    monkeypatch.setenv("SMTP_USERNAME", "founder@plantiers.com")
    monkeypatch.setenv("SMTP_PASSWORD", secrets.token_hex(8))
    mail_provider._reach_cache.clear()
    yield
    mail_provider._reach_cache.clear()


class Conn:
    def __init__(self, fail=None):
        self.fail, self.calls = fail, []

    def __call__(self, address, timeout):
        self.calls.append((address, timeout))
        if self.fail:
            raise self.fail
        return self

    def close(self):
        pass


def test_a_closed_smtp_port_is_not_working_and_says_why_without_any_secret():
    conn = Conn(ConnectionRefusedError("refused"))
    out = mail_provider.reachable(connect=conn)
    assert out == {
        "ok": False,
        "provider": "smtp",
        "host": "smtp.hostinger.com",
        "port": 587,
        "error": "ConnectionRefusedError",
    }
    assert conn.calls == [(("smtp.hostinger.com", 587), mail_provider.REACH_TIMEOUT)]


def test_an_open_port_is_reachable_and_the_probe_is_cached_then_redone():
    conn, now = Conn(), [1000.0]
    assert mail_provider.reachable(connect=conn, clock=lambda: now[0])["ok"] is True
    mail_provider.reachable(connect=conn, clock=lambda: now[0] + 60)
    assert len(conn.calls) == 1  # within REACH_TTL: no second connection
    mail_provider.reachable(connect=conn, clock=lambda: now[0] + mail_provider.REACH_TTL + 1)
    assert len(conn.calls) == 2


def test_brevo_is_probed_on_https_before_smtp_and_nothing_configured_is_not_working(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-" + "0" * 16)
    conn = Conn()
    assert mail_provider.reachable(connect=conn)["provider"] == "brevo"
    assert conn.calls[0][0] == ("api.brevo.com", 443)
    for name in ("BREVO_API_KEY", "SMTP_HOST"):
        monkeypatch.delenv(name)
    assert mail_provider.reachable(connect=Conn())["error"] == "not_configured"


def test_the_in_process_test_recorder_is_always_reachable(monkeypatch):
    monkeypatch.setenv("OUTREACH_TEST_SINK", "true")
    conn = Conn(ConnectionRefusedError())
    assert mail_provider.reachable(connect=conn)["ok"] is True and conn.calls == []
