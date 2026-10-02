"""The SMTP adapter, offline: `smtplib` is replaced by a recorder, no socket is ever opened.

Real delivery from founder@plantiers.com is NOT exercised here (it needs the real credentials and a network): these
tests pin the protocol steps, the TLS verification settings, the error classification and the secrecy of the password.
"""

import secrets
import smtplib
import socket
import ssl

import pytest

from services import smtp_svc
from services.outreach_os.channels import ChannelMessage, unsubscribe_headers

PASSWORD = secrets.token_hex(12)  # generated per run: never a literal credential in the repository


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to open a real network connection")

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example")
    monkeypatch.setenv("SMTP_USERNAME", "founder@plantiers.com")
    monkeypatch.setenv("SMTP_PASSWORD", PASSWORD)
    for name in ("SMTP_PORT", "SMTP_SECURITY", "OUTREACH_SANDBOX", "OUTREACH_LIVE_ALLOWLIST"):
        monkeypatch.delenv(name, raising=False)


def message(**kw):
    base = dict(
        to="prospect@restaurant.example",
        subject="Votre visibilité en ligne",
        body="Bonjour,\nÉcrit par Plantiers.\nhttps://app.example/api/unsubscribe/tok.sig\n",
        sender_name="Noé Plantier",
        sender_email="founder@plantiers.com",
        idempotency_key="k1",
        headers=unsubscribe_headers("https://app.example/api/unsubscribe/tok.sig"),
    )
    return ChannelMessage(**{**base, **kw})


class FakeSMTP:
    """Records the calls; `fail` maps a method name to the exception it raises."""

    instances: list = []
    fail: dict = {}
    starttls_supported = True

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.calls: list = []
        FakeSMTP.instances.append(self)
        self._maybe_fail("connect")

    def _maybe_fail(self, name):
        if name in FakeSMTP.fail:
            raise FakeSMTP.fail[name]

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self, context=None):
        self.calls.append("starttls")
        self.starttls_context = context
        if not FakeSMTP.starttls_supported:
            raise smtplib.SMTPNotSupportedError("STARTTLS extension not supported by server.")

    def login(self, user, password):
        self.calls.append("login")
        self.credentials = (user, password)
        self._maybe_fail("login")

    def send_message(self, msg, from_addr=None, to_addrs=None):
        self.calls.append("send_message")
        self.sent = (msg, from_addr, to_addrs)
        self._maybe_fail("send_message")

    def quit(self):
        self.calls.append("quit")

    def close(self):
        self.calls.append("close")


class FakeSMTPSSL(FakeSMTP):
    pass


@pytest.fixture()
def fake(monkeypatch, env):
    FakeSMTP.instances, FakeSMTP.fail, FakeSMTP.starttls_supported = [], {}, True
    monkeypatch.setattr(smtp_svc.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtp_svc.smtplib, "SMTP_SSL", FakeSMTPSSL)
    return FakeSMTP


def adapter(allowlist=None):
    return smtp_svc.SmtpEmailAdapter(smtp_svc.SmtpConfig.from_env(), allowlist)


# ---- configuration --------------------------------------------------------------------------------------
def test_config_defaults_follow_the_security_mode(env, monkeypatch):
    cfg = smtp_svc.SmtpConfig.from_env()
    assert (cfg.host, cfg.port, cfg.security) == ("smtp.example", 587, "starttls")
    monkeypatch.setenv("SMTP_SECURITY", "SSL")
    assert smtp_svc.SmtpConfig.from_env().port == 465
    monkeypatch.setenv("SMTP_PORT", "2525")
    assert smtp_svc.SmtpConfig.from_env().port == 2525


@pytest.mark.parametrize(
    "name, value",
    [
        ("SMTP_HOST", ""),
        ("SMTP_USERNAME", ""),
        ("SMTP_PASSWORD", ""),
        ("SMTP_SECURITY", "none"),
        ("SMTP_SECURITY", "plain"),
        ("SMTP_PORT", "abc"),
        ("SMTP_PORT", "0"),
        ("SMTP_PORT", "70000"),
    ],
)
def test_an_incomplete_or_unsafe_configuration_is_not_configured(env, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    assert smtp_svc.SmtpConfig.from_env() is None
    assert not smtp_svc.is_configured() and smtp_svc.adapter_from_env() is None


def test_the_password_never_appears_in_repr_or_status(env):
    cfg = smtp_svc.SmtpConfig.from_env()
    assert PASSWORD not in repr(cfg) and PASSWORD not in str(cfg)
    assert smtp_svc.status() == {"configured": True, "host": "smtp.example", "security": "starttls"}


def test_adapter_from_env_applies_the_sandbox_allowlist(env, monkeypatch):
    monkeypatch.setenv("OUTREACH_LIVE_ALLOWLIST", "a@x.example")
    assert smtp_svc.adapter_from_env()._allowlist == ("a@x.example",)  # sandbox is on by default
    assert smtp_svc.adapter_from_env(extra_allowed=("me@x.example",))._allowlist == ("a@x.example", "me@x.example")
    monkeypatch.setenv("OUTREACH_SANDBOX", "false")
    assert smtp_svc.adapter_from_env()._allowlist is None


# ---- message --------------------------------------------------------------------------------------------
def test_the_message_carries_identity_unsubscribe_headers_and_survives_accents():
    msg = smtp_svc.build_message(message())
    assert str(msg["From"]) == "Noé Plantier <founder@plantiers.com>"
    assert msg["To"] == "prospect@restaurant.example" and msg["Reply-To"] == "founder@plantiers.com"
    assert msg["List-Unsubscribe"] == "<https://app.example/api/unsubscribe/tok.sig>"
    assert msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert msg["Message-ID"].endswith("@plantiers.com>")
    assert "Écrit par Plantiers" in msg.get_content()  # accents round-trip through quoted-printable
    assert msg.as_bytes().isascii()  # safe for a server without 8BITMIME


def test_a_line_break_in_the_subject_cannot_inject_a_header():
    msg = smtp_svc.build_message(message(subject="Hello\r\nBcc: victim@evil.example"))
    assert msg["Bcc"] is None
    assert "\n" not in msg["Subject"] and "\r" not in msg["Subject"]


# ---- protocol -------------------------------------------------------------------------------------------
def test_starttls_flow_verifies_the_certificate_and_authenticates_before_sending(fake):
    result = adapter().send(message())
    assert result.status == "sent" and result.simulated is False
    assert result.provider_id and result.provider_id.endswith("@plantiers.com")
    client = fake.instances[0]
    assert client.calls == ["ehlo", "starttls", "ehlo", "login", "send_message", "quit"]
    assert (client.host, client.port, client.timeout) == ("smtp.example", 587, smtp_svc.TIMEOUT_SECONDS)
    assert client.starttls_context.verify_mode == ssl.CERT_REQUIRED and client.starttls_context.check_hostname is True
    assert client.credentials == ("founder@plantiers.com", PASSWORD)
    _, from_addr, to_addrs = client.sent
    assert (from_addr, to_addrs) == ("founder@plantiers.com", ["prospect@restaurant.example"])


def test_implicit_ssl_flow(fake, monkeypatch):
    monkeypatch.setenv("SMTP_SECURITY", "ssl")
    result = adapter().send(message())
    client = fake.instances[0]
    assert isinstance(client, FakeSMTPSSL) and client.port == 465 and result.status == "sent"
    assert client.context.verify_mode == ssl.CERT_REQUIRED and client.context.check_hostname is True
    assert "starttls" not in client.calls


def test_a_server_without_starttls_is_refused_and_the_password_is_never_sent(fake):
    fake.starttls_supported = False
    result = adapter().send(message())
    assert result.status == "failed"
    assert "login" not in fake.instances[0].calls and "send_message" not in fake.instances[0].calls


# ---- errors ---------------------------------------------------------------------------------------------
def test_authentication_failure_is_failed_and_the_password_is_redacted(fake):
    fake.fail = {"login": smtplib.SMTPAuthenticationError(535, f"5.7.8 bad credentials {PASSWORD}".encode())}
    result = adapter().send(message())
    assert result.status == "failed" and "authentication failed" in result.error and "535" in result.error
    assert PASSWORD not in result.error and "***" in result.error
    assert "send_message" not in fake.instances[0].calls


def test_a_refused_recipient_is_failed(fake):
    fake.fail = {"send_message": smtplib.SMTPRecipientsRefused({"prospect@restaurant.example": (550, b"no such user")})}
    result = adapter().send(message())
    assert result.status == "failed" and "recipient" in result.error


def test_a_server_rejection_after_data_is_failed_with_its_code(fake):
    fake.fail = {"send_message": smtplib.SMTPDataError(554, b"5.7.1 message rejected as spam")}
    result = adapter().send(message())
    assert result.status == "failed" and "554" in result.error


def test_connection_refused_is_failed_with_the_phase_not_the_details(fake):
    fake.fail = {"connect": ConnectionRefusedError("[Errno 111] refused to smtp.example:587")}
    result = adapter().send(message())
    assert result.status == "failed" and result.error == "connect failed (ConnectionRefusedError)"


def test_a_certificate_problem_is_failed(fake):
    fake.fail = {"connect": ssl.SSLCertVerificationError("certificate verify failed")}
    result = adapter().send(message())
    assert result.status == "failed" and "TLS" in result.error


def test_a_connection_lost_while_sending_is_unknown_never_failed(fake):
    fake.fail = {"send_message": smtplib.SMTPServerDisconnected("Connection unexpectedly closed")}
    result = adapter().send(message())
    assert result.status == "unknown" and "outcome unknown" in result.error and result.provider_id is None


# ---- guards ---------------------------------------------------------------------------------------------
def test_the_sandbox_refuses_other_recipients_before_any_connection(fake):
    sandboxed = adapter(allowlist=("founder@plantiers.com",))
    result = sandboxed.send(message(to="prospect@restaurant.example"))
    assert result.status == "failed" and "allowlist" in result.error
    assert fake.instances == []  # no connection was even attempted
    assert sandboxed.send(message(to="founder@plantiers.com")).status == "sent"


def test_an_empty_sandbox_allowlist_allows_nobody(fake):
    assert adapter(allowlist=()).send(message()).status == "failed" and fake.instances == []


@pytest.mark.parametrize(
    "change, expected",
    [
        ({"to": "not-an-address"}, "invalid recipient"),
        ({"subject": "  "}, "empty subject or body"),
        ({"body": ""}, "empty subject or body"),
        ({"headers": {}}, "List-Unsubscribe"),
        ({"sender_email": "nope"}, "invalid sender"),
    ],
)
def test_a_malformed_message_is_refused_without_a_connection(fake, change, expected):
    result = adapter().send(message(**change))
    assert result.status == "failed" and expected in result.error and fake.instances == []


def test_the_connection_is_closed_even_when_sending_fails(fake):
    fake.fail = {"send_message": smtplib.SMTPDataError(554, b"rejected")}
    adapter().send(message())
    assert fake.instances[0].calls[-1] == "quit"
