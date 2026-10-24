"""IMAP adapter with `imaplib` replaced by a recorder: no network, TLS always on, password never exposed."""

import imaplib
import uuid

import pytest

from services import imap_svc

PASSWORD = uuid.uuid4().hex  # generated per run: no credential-looking literal in the repository
ENV = {"IMAP_HOST": "imap.example.test", "IMAP_USERNAME": "founder@plantiers.com", "IMAP_PASSWORD": PASSWORD}


@pytest.fixture()
def configured(monkeypatch):
    for k in ("IMAP_PORT", "IMAP_FOLDER"):
        monkeypatch.delenv(k, raising=False)
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)


class FakeImap:
    instances: list = []

    def __init__(self, host, port, ssl_context=None, timeout=None):
        self.host, self.port, self.ctx, self.timeout = host, port, ssl_context, timeout
        self.calls: list = []
        FakeImap.instances.append(self)

    def login(self, user, password):
        self.calls.append(("login",))

    def select(self, folder):
        self.calls.append(("select", folder))
        return "OK", [b"1"]

    def uid(self, command, *args):
        self.calls.append((command, *args))
        if command == "SEARCH":
            return "OK", [b"7 9"]
        if command == "FETCH":
            return "OK", [(b"1 (UID 7 BODY[] {5}", b"hello"), b")"]
        return "OK", [b""]

    def close(self):
        pass

    def logout(self):
        pass


def test_it_is_not_configured_without_all_three_settings(monkeypatch):
    for k in ENV:
        monkeypatch.delenv(k, raising=False)
    assert imap_svc.ImapConfig.from_env() is None and imap_svc.mailbox_from_env() is None
    monkeypatch.setenv("IMAP_HOST", "h")
    assert imap_svc.is_configured() is False  # a partial configuration is never a configuration


def test_status_never_exposes_the_username_or_the_password(configured):
    status = imap_svc.status()
    assert status == {"configured": True, "host": "imap.example.test"}
    config = imap_svc.ImapConfig.from_env()
    assert PASSWORD not in repr(config) and config.port == 993 and config.folder == "INBOX"


def test_a_bad_port_is_not_a_configuration(configured, monkeypatch):
    monkeypatch.setenv("IMAP_PORT", "abc")
    assert imap_svc.ImapConfig.from_env() is None
    monkeypatch.setenv("IMAP_PORT", "70000")
    assert imap_svc.ImapConfig.from_env() is None


def test_fetch_uses_verified_tls_and_peek_and_marks_seen_separately(configured, monkeypatch):
    FakeImap.instances.clear()
    monkeypatch.setattr(imaplib, "IMAP4_SSL", FakeImap)
    box = imap_svc.mailbox_from_env()
    fetched = box.fetch_unseen(limit=1)
    assert fetched == [(b"7", b"hello")]  # limited to one message
    first = FakeImap.instances[0]
    assert (
        first.port == 993
        and first.timeout == imap_svc.TIMEOUT_SECONDS
        and first.ctx.verify_mode.name == "CERT_REQUIRED"
    )
    fetch_call = next(c for c in first.calls if c[0] == "FETCH")
    assert "BODY.PEEK" in fetch_call[2]  # reading never flags a message
    assert not any(c[0] == "STORE" for c in first.calls)

    box.mark_seen([b"7"])
    store = next(c for c in FakeImap.instances[1].calls if c[0] == "STORE")
    assert store[1:] == ("7", "+FLAGS", "(\\Seen)")
