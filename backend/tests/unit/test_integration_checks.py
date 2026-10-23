"""The live checks, replayed offline: no socket is opened and no secret is returned."""

import imaplib
import smtplib

import pytest

from services import imap_svc
from services import integration_checks as checks
from services import registry_svc, sendgrid_svc, smtp_svc, twilio_svc

PASSWORD = "pw-" + "x" * 12  # runtime-built, not a credential


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def refuse(*a, **k):
        raise AssertionError("network access in a unit test")

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def test_database_result_shapes():
    ok = checks.database(7, None)
    assert ok["outcome"] == "passed" and ok["latency_ms"] == 7
    bad = checks.database(None, "down")
    assert bad["outcome"] == "failed" and bad["ok"] is False


def test_osm_passes_when_any_server_answers_and_fails_when_none_does():
    answers = iter([{"host": "a", "ok": False, "error": "TimeoutError: x"}, {"host": "b", "ok": True, "ms": 120}])
    seen = []

    def probe(endpoint):
        seen.append(endpoint)
        return next(answers, {"host": "z", "ok": False, "status": 504})

    result = checks.osm(probe)
    assert result["outcome"] == "passed" and "b: 120 ms" in result["detail"]
    assert len(seen) >= 2  # every server is probed, one after the other
    down = checks.osm(lambda e: {"host": "h", "ok": False, "status": 504})
    assert down["outcome"] == "failed" and "browser" in down["detail"]


def test_registry_respects_the_network_flag(monkeypatch):
    monkeypatch.delenv("FEATURE_EXTERNAL_SOURCES", raising=False)
    called = []
    skipped = checks.registry(lambda p: called.append(p) or {})
    assert skipped["outcome"] == "skipped" and not called
    monkeypatch.setenv("FEATURE_EXTERNAL_SOURCES", "true")
    assert checks.registry(lambda p: {"total_results": 42})["outcome"] == "passed"

    def unavailable(params):
        raise registry_svc.Unavailable("the company registry answered HTTP 429; try again in a minute")

    failed = checks.registry(unavailable)
    assert failed["outcome"] == "failed" and "429" in failed["detail"]


def test_smtp_and_imap_are_skipped_when_incomplete(monkeypatch):
    for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "IMAP_HOST", "IMAP_USERNAME", "IMAP_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    assert checks.smtp()["outcome"] == "skipped"
    assert checks.imap()["outcome"] == "skipped"


class FakeSMTP:
    log: list = []
    fail_login = False

    def __init__(self, host, port, timeout=None, context=None):
        self.log = FakeSMTP.log = [("connect", host, port)]

    def ehlo(self):
        self.log.append("ehlo")

    def starttls(self, context=None):
        self.log.append("starttls")

    def login(self, user, password):
        self.log.append("login")
        if FakeSMTP.fail_login:
            raise smtplib.SMTPAuthenticationError(535, f"bad credentials for {password}".encode())

    def send_message(self, *a, **k):
        raise AssertionError("a connection check must never send")

    def sendmail(self, *a, **k):
        raise AssertionError("a connection check must never send")

    def quit(self):
        self.log.append("quit")

    def close(self):
        self.log.append("close")


def smtp_config(security="starttls"):
    return smtp_svc.SmtpConfig(
        host="smtp.example", port=587, username="u@example.test", password=PASSWORD, security=security
    )


def test_smtp_connection_check_signs_in_and_never_sends(monkeypatch):
    FakeSMTP.fail_login = False
    monkeypatch.setattr(smtp_svc.smtplib, "SMTP", FakeSMTP)
    answer = smtp_svc.check_connection(smtp_config())
    assert answer == {"ok": True, "phase": "login", "error": None}
    assert FakeSMTP.log == [("connect", "smtp.example", 587), "ehlo", "starttls", "ehlo", "login", "quit"]


def test_smtp_connection_check_redacts_the_password_from_errors(monkeypatch):
    FakeSMTP.fail_login = True
    monkeypatch.setattr(smtp_svc.smtplib, "SMTP", FakeSMTP)
    answer = smtp_svc.check_connection(smtp_config())
    assert answer["ok"] is False and answer["phase"] == "login" and "535" in answer["error"]
    assert PASSWORD not in answer["error"]


def test_smtp_check_runner_reports_a_failure_with_the_step(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example")
    monkeypatch.setenv("SMTP_USERNAME", "u@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", PASSWORD)
    monkeypatch.delenv("SMTP_SECURITY", raising=False)
    monkeypatch.delenv("SMTP_PORT", raising=False)
    result = checks.smtp(lambda: {"ok": False, "phase": "starttls", "error": "starttls failed (SMTPNotSupportedError)"})
    assert result["outcome"] == "failed" and "starttls" in result["detail"] and PASSWORD not in result["detail"]
    assert checks.smtp(lambda: {"ok": True, "phase": "login", "error": None})["outcome"] == "passed"


class FakeIMAP:
    log: list = []
    reject = False

    def __init__(self, host, port, ssl_context=None, timeout=None):
        FakeIMAP.log = [("connect", host, port)]

    def login(self, user, password):
        FakeIMAP.log.append("login")
        if FakeIMAP.reject:
            raise imaplib.IMAP4.error(f"[AUTHENTICATIONFAILED] {password}")

    def select(self, folder, readonly=False):
        FakeIMAP.log.append(("select", folder, readonly))
        return "OK", [b"1"]

    def uid(self, *a, **k):
        raise AssertionError("a connection check must not touch messages")

    def close(self):
        FakeIMAP.log.append("close")

    def logout(self):
        FakeIMAP.log.append("logout")


def imap_config():
    return imap_svc.ImapConfig(host="imap.example", username="u@example.test", password=PASSWORD)


def test_imap_connection_check_opens_read_only(monkeypatch):
    FakeIMAP.reject = False
    monkeypatch.setattr(imap_svc.imaplib, "IMAP4_SSL", FakeIMAP)
    assert imap_svc.check_connection(imap_config()) == {"ok": True, "phase": "folder", "error": None}
    assert ("select", "INBOX", True) in FakeIMAP.log  # read-only


def test_imap_connection_check_never_echoes_the_server_text(monkeypatch):
    FakeIMAP.reject = True
    monkeypatch.setattr(imap_svc.imaplib, "IMAP4_SSL", FakeIMAP)
    answer = imap_svc.check_connection(imap_config())
    assert answer["ok"] is False and answer["phase"] == "login" and PASSWORD not in answer["error"]


class _Resp:
    def __init__(self, code):
        self.status_code = code


class _Scopes:
    def __init__(self, code=None, exc=None):
        self.code, self.exc = code, exc

    def get(self):
        if self.exc:
            raise self.exc
        return _Resp(self.code)


class FakeSendGrid:
    def __init__(self, key, code=200, exc=None):
        self.client = type("C", (), {"scopes": _Scopes(code, exc)})()


class _HTTPError(Exception):
    def __init__(self, status_code):
        self.status_code = status_code


def test_sendgrid_check_distinguishes_a_rejected_key_from_an_outage(monkeypatch):
    monkeypatch.setattr(sendgrid_svc, "API_KEY", PASSWORD)
    monkeypatch.setattr(sendgrid_svc, "FROM_EMAIL", "founder@plantiers.com")
    assert checks.sendgrid(lambda key: FakeSendGrid(key))["outcome"] == "passed"
    rejected = checks.sendgrid(lambda key: FakeSendGrid(key, exc=_HTTPError(401)))
    assert rejected["outcome"] == "failed" and "rejected" in rejected["detail"] and PASSWORD not in rejected["detail"]
    outage = checks.sendgrid(lambda key: FakeSendGrid(key, exc=TimeoutError("boom " + PASSWORD)))
    assert outage["outcome"] == "failed" and "TimeoutError" in outage["detail"] and PASSWORD not in outage["detail"]


def test_sendgrid_and_twilio_are_skipped_when_not_configured(monkeypatch):
    monkeypatch.setattr(sendgrid_svc, "API_KEY", None)
    monkeypatch.setattr(twilio_svc, "SID", None)
    assert checks.sendgrid()["outcome"] == "skipped"
    assert checks.twilio()["outcome"] == "skipped"


def test_twilio_check_reads_the_account_and_flags_a_suspended_one(monkeypatch):
    monkeypatch.setattr(twilio_svc, "SID", "AC" + "0" * 32)
    monkeypatch.setattr(twilio_svc, "TOKEN", PASSWORD)

    def client_for(status=None, exc=None):
        class Accounts:
            def __init__(self, sid):
                pass

            def fetch(self):
                if exc:
                    raise exc
                return type("A", (), {"status": status})()

        class Api:
            accounts = staticmethod(lambda sid: Accounts(sid))

        return lambda sid, token: type("T", (), {"api": Api})()

    assert checks.twilio(client_for("active"))["outcome"] == "passed"
    assert "suspended" in checks.twilio(client_for("suspended"))["detail"]
    rejected = checks.twilio(client_for(exc=_HTTPError(401)))
    assert rejected["outcome"] == "failed" and "rejected" in rejected["detail"] and PASSWORD not in rejected["detail"]
