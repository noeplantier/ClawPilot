"""The mailbox diagnosis, offline: fakes for every network effect, a local UDP socket for the DNS client.

No step opens a connection to a real server, and none sends a message: that is asserted, not assumed."""

import socket
import ssl
import struct
import threading
from datetime import datetime, timedelta, timezone

import pytest

from services import imap_svc
from services import mail_diagnostics as md
from services import smtp_svc

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=timezone.utc)
PASSWORD = "pw-" + "q" * 12  # a throwaway value: the tests check that it never shows up in a result


def _smtp(port=587, security="starttls", host="smtp.mailhost.example"):
    return smtp_svc.SmtpConfig(
        host=host, port=port, username="founder@plantiers.example", password=PASSWORD, security=security
    )


def _imap(port=993):
    return imap_svc.ImapConfig(
        host="imap.mailhost.example", username="founder@plantiers.example", password=PASSWORD, port=port
    )


def _cert(days):
    return {"notAfter": (NOW + timedelta(days=days)).strftime("%b %d %H:%M:%S %Y GMT")}


def _by(result, scope, id_):
    return next(s for s in result["steps"] if s["scope"] == scope and s["id"] == id_)


class Hooks:
    """Records what the run did; `sent` stays empty because nothing in the diagnosis can send."""

    def __init__(self, *, cert=None, tls_error=None, smtp_ok=True, imap_ok=True, dns=None, resolve_error=None):
        self.cert = cert if cert is not None else _cert(60)
        self.tls_error, self.resolve_error = tls_error, resolve_error
        self.smtp_ok, self.imap_ok = smtp_ok, imap_ok
        self.dns = dns if dns is not None else {}
        self.calls = []

    def resolve(self, host):
        self.calls.append(("resolve", host))
        if self.resolve_error:
            raise self.resolve_error
        return [("addr",)]

    def tls(self, host, port, mode):
        self.calls.append(("tls", port, mode))
        if self.tls_error:
            raise self.tls_error
        return self.cert

    def smtp_check(self, config=None):
        self.calls.append(("smtp_auth",))
        return (
            {"ok": True, "phase": "login", "error": None}
            if self.smtp_ok
            else {"ok": False, "phase": "login", "error": "authentication failed (535)"}
        )

    def imap_check(self, config=None):
        self.calls.append(("imap_folder",))
        return (
            {"ok": True, "phase": "folder", "error": None}
            if self.imap_ok
            else {"ok": False, "phase": "login", "error": "the server refused the request"}
        )

    def txt(self, name):
        self.calls.append(("txt", name))
        return self.dns.get(name, [])

    def run(self, **kw):
        return md.run(
            now=NOW,
            resolve=self.resolve,
            tls=self.tls,
            smtp_check=self.smtp_check,
            imap_check=self.imap_check,
            txt=self.txt,
            **kw
        )


GOOD_DNS = {
    "plantiers.example": ["v=spf1 include:_spf.mailhost.example ~all"],
    "_dmarc.plantiers.example": ["v=DMARC1; p=quarantine; rua=mailto:d@plantiers.example"],
    "hostingermail1._domainkey.plantiers.example": ["v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3"],
}


# ---------------------------------------------------------------- port and security coherence
@pytest.mark.parametrize(
    "port,security,status",
    [
        (587, "starttls", md.PASSED),
        (465, "ssl", md.PASSED),
        (465, "starttls", md.FAILED),
        (587, "ssl", md.FAILED),
        (2626, "ssl", md.WARNING),
    ],
)
def test_the_port_must_speak_the_security_mode_asked(port, security, status):
    [finding] = md.smtp_findings("h", port, security)
    assert finding["status"] == status
    if status == md.FAILED:
        assert "SMTP_SECURITY=" in finding["detail"]  # says what to change


def test_the_imap_reader_only_speaks_implicit_tls():
    assert md.imap_findings("h", 993)[0]["status"] == md.PASSED
    assert md.imap_findings("h", 143)[0]["status"] == md.FAILED


# ---------------------------------------------------------------- certificate
def test_a_certificate_is_judged_by_its_remaining_days():
    assert md.cert_finding("smtp", _cert(60), NOW)["status"] == md.PASSED
    assert md.cert_finding("smtp", _cert(5), NOW)["status"] == md.WARNING
    expired = md.cert_finding("smtp", _cert(-3), NOW)
    assert expired["status"] == md.FAILED and "expiré" in expired["detail"]
    assert md.cert_finding("smtp", None, NOW)["status"] == md.WARNING  # connected, certificate unreadable: not "fine"


# ---------------------------------------------------------------- the whole run
def test_a_healthy_mailbox_passes_every_step_and_nothing_is_sent():
    hooks = Hooks(dns=GOOD_DNS)
    result = hooks.run(smtp_config=_smtp(), imap_config=_imap(), sender_email="founder@plantiers.example")
    assert result["ok"] is True and result["failed"] == 0 and result["warnings"] == 0
    assert [s["id"] for s in result["steps"] if s["scope"] == "smtp"] == ["config", "dns", "tls", "auth"]
    assert [s["id"] for s in result["steps"] if s["scope"] == "imap"] == ["config", "dns", "tls", "folder"]
    assert {s["id"] for s in result["steps"] if s["scope"] == "sender"} == {"spf", "dmarc", "dkim"}
    assert (
        "Aucun message n'a été envoyé" in result["notes"][0]
        and "ne garantit pas la délivrabilité" in result["notes"][1]
    )
    assert not any(
        call[0] == "send" for call in hooks.calls
    )  # the only effects are lookups, TLS, sign-ins, TXT queries


def test_an_unresolvable_host_stops_that_mailbox_and_says_so():
    hooks = Hooks(resolve_error=socket.gaierror("nope"))
    result = hooks.run(smtp_config=_smtp(), imap_config=None, sender_email=None)
    assert _by(result, "smtp", "dns")["status"] == md.FAILED
    assert _by(result, "smtp", "auth")["status"] == md.SKIPPED  # no sign-in attempt on a host that does not exist
    assert ("smtp_auth",) not in hooks.calls and result["ok"] is False


def test_a_tls_failure_is_reported_without_a_sign_in():
    hooks = Hooks(tls_error=ssl.SSLCertVerificationError("hostname mismatch"))
    result = hooks.run(smtp_config=_smtp(), imap_config=None, sender_email=None)
    assert _by(result, "smtp", "tls")["status"] == md.FAILED and "nom d'hôte" in _by(result, "smtp", "tls")["detail"]
    assert _by(result, "smtp", "auth")["status"] == md.SKIPPED and ("smtp_auth",) not in hooks.calls


def test_a_closed_port_is_reported_as_such():
    result = Hooks(tls_error=TimeoutError()).run(smtp_config=_smtp(), imap_config=None, sender_email=None)
    assert "port fermé" in _by(result, "smtp", "tls")["detail"] and result["ok"] is False


def test_a_refused_password_is_reported_with_the_phase_and_never_the_password():
    result = Hooks(smtp_ok=False).run(smtp_config=_smtp(), imap_config=_imap(), sender_email=None)
    auth = _by(result, "smtp", "auth")
    assert auth["status"] == md.FAILED and "535" in auth["detail"] and "login" in auth["detail"]
    assert PASSWORD not in repr(result) and "founder@plantiers.example" not in repr(result["steps"])


def test_missing_configuration_is_skipped_and_never_a_success():
    result = Hooks().run(smtp_config=None, imap_config=None, sender_email=None)
    assert [s["status"] for s in result["steps"]] == [md.SKIPPED, md.SKIPPED, md.SKIPPED]
    assert result["ok"] is True and result["failed"] == 0  # nothing failed, but nothing was proven either
    assert "ne sont pas lues" in _by(result, "imap", "config")["detail"]


def test_the_dns_prerequisites_are_warnings_when_absent_and_a_conflict_is_a_failure():
    result = Hooks(dns={}).run(smtp_config=None, imap_config=None, sender_email="founder@plantiers.example")
    assert [_by(result, "sender", i)["status"] for i in ("spf", "dmarc", "dkim")] == [md.WARNING] * 3
    assert result["ok"] is True  # missing records are a risk of spam, not a proof of failure
    double = Hooks(dns={"plantiers.example": ["v=spf1 a ~all", "v=spf1 mx ~all"]}).run(
        smtp_config=None, imap_config=None, sender_email="founder@plantiers.example"
    )
    assert _by(double, "sender", "spf")["status"] == md.FAILED


def test_a_dns_outage_is_reported_as_not_checked():
    def broken(name):
        raise md.DnsError("the DNS query failed (timeout)")

    result = md.run(now=NOW, smtp_config=None, imap_config=None, sender_email="a@plantiers.example", txt=broken)
    assert (
        _by(result, "sender", "spf")["status"] == md.SKIPPED and "non vérifié" in _by(result, "sender", "spf")["detail"]
    )


# ---------------------------------------------------------------- the DNS client, against a local fake resolver
def _answer(query, texts, *, rcode=0, truncated=False):
    ident = query[:2]
    flags = 0x8180 | rcode | (0x0200 if truncated else 0)
    question = query[12:]
    out = ident + struct.pack("!HHHHH", flags, 1, 0 if truncated else len(texts), 0, 0) + question
    if truncated:
        return out
    for text in texts:
        raw = text.encode()
        rdata = b"".join(
            bytes([len(raw[i : i + 255])]) + raw[i : i + 255] for i in range(0, len(raw), 255)
        )  # >255: chunks
        out += b"\xc0\x0c" + struct.pack("!HHIH", 16, 1, 60, len(rdata)) + rdata  # name = pointer to the question
    return out


@pytest.fixture()
def fake_resolver():
    """A UDP resolver on localhost: serves the TXT records it is given, counts the questions."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(5)
    state = {"records": {}, "rcode": 0, "asked": []}

    def serve():
        try:
            while True:
                data, addr = sock.recvfrom(512)
                name = _qname(data)
                state["asked"].append(name)
                sock.sendto(_answer(data, state["records"].get(name, []), rcode=state["rcode"]), addr)
        except OSError:
            return

    def _qname(data):
        labels, pos = [], 12
        while data[pos]:
            labels.append(data[pos + 1 : pos + 1 + data[pos]].decode())
            pos += 1 + data[pos]
        return ".".join(labels)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield sock.getsockname()[1], state
    sock.close()


def test_txt_lookup_reads_a_compressed_multi_string_answer(fake_resolver):
    port, state = fake_resolver
    long_record = "v=DKIM1; k=rsa; p=" + "A" * 300  # longer than one TXT string: stored in several, joined back
    state["records"]["plantiers.example"] = ["v=spf1 include:_spf.mailhost.example ~all", long_record]
    found = md.txt_lookup("plantiers.example", nameserver="127.0.0.1", port=port, timeout=3)
    assert found == ["v=spf1 include:_spf.mailhost.example ~all", long_record]
    assert state["asked"] == ["plantiers.example"]  # one question, to the resolver given


def test_txt_lookup_returns_nothing_for_a_name_that_does_not_exist(fake_resolver):
    port, state = fake_resolver
    state["rcode"] = 3  # NXDOMAIN
    assert md.txt_lookup("_dmarc.nothing.example", nameserver="127.0.0.1", port=port, timeout=3) == []


def test_txt_lookup_reports_a_resolver_error_and_an_unreachable_resolver(fake_resolver):
    port, state = fake_resolver
    state["rcode"] = 2  # SERVFAIL
    with pytest.raises(md.DnsError, match="error code 2"):
        md.txt_lookup("plantiers.example", nameserver="127.0.0.1", port=port, timeout=3)
    with pytest.raises(md.DnsError):
        md.txt_lookup("plantiers.example", nameserver="127.0.0.1", port=1, timeout=0.3)  # nothing listens there


def test_a_resolver_is_read_from_resolv_conf(tmp_path):
    conf = tmp_path / "resolv.conf"
    conf.write_text("# comment\nsearch example\nnameserver ::1\nnameserver 10.0.0.2\n")
    assert md.system_nameserver(str(conf)) == "10.0.0.2"  # the IPv4 one: the client speaks IPv4
    assert md.system_nameserver(str(tmp_path / "missing")) is None
