"""Technical diagnostics of the mailbox: name resolution, port and security coherence, TLS certificate, sign-in,
read-only IMAP folder, and the DNS records a receiving server looks at (SPF, DKIM hint, DMARC) for the sender's domain.

No step sends a message: the SMTP sign-in stops before MAIL FROM, the IMAP folder is opened read-only. Every network
effect goes through an injectable hook, so the tests run on fakes and never touch a network. Nothing here runs by
itself: the owner presses a button (`POST /api/settings/email/diagnostics`); a diagnosis of production credentials is
an action to ask for, never a background habit. No credential, address or user name appears in a result or a log.

The DNS records are PREREQUISITES. Having them does not guarantee delivery, and their absence is a reason to expect
spam folders, not a proof of failure.
"""

from __future__ import annotations

import os
import socket
import ssl
import struct
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from services import imap_svc, smtp_svc

PASSED, FAILED, WARNING, SKIPPED = "passed", "failed", "warning", "skipped"

# The mailbox provider's documented endpoints: a hint, never a reason to reject another host.
HOSTINGER = {"smtp": {465: "ssl", 587: "starttls"}, "imap": {993: "ssl"}}
# Selectors Hostinger Mail publishes for DKIM; another provider uses other names, so absence proves nothing.
DKIM_SELECTORS = ("hostingermail1", "hostingermail2", "hostingermail3")
CERT_WARN_DAYS = 14


def _step(id_: str, scope: str, status: str, detail: str) -> dict[str, str]:
    return {"id": id_, "scope": scope, "status": status, "detail": detail}


# ---------------------------------------------------------------------------------------------- pure findings
def smtp_findings(host: str, port: int, security: str) -> list[dict[str, str]]:
    """Is the port the one this security mode speaks? A mismatch is the commonest silent cause of a timeout."""
    expected = {465: "ssl", 587: "starttls", 25: "starttls", 2525: "starttls"}.get(port)
    if expected is None:
        return [
            _step("config", "smtp", WARNING, f"Port {port} inhabituel : 465 (ssl) ou 587 (starttls) sont les usuels.")
        ]
    if expected != security:
        return [
            _step(
                "config",
                "smtp",
                FAILED,
                f"Le port {port} parle {expected}, mais SMTP_SECURITY vaut {security} : la connexion échouera ou "
                f"restera bloquée. Utilisez SMTP_SECURITY={expected}, ou le port {465 if security == 'ssl' else 587}.",
            )
        ]
    return [_step("config", "smtp", PASSED, f"Port {port} et mode {security} sont cohérents.")]


def imap_findings(host: str, port: int) -> list[dict[str, str]]:
    """The reader speaks implicit TLS only (imaplib.IMAP4_SSL): port 143 (STARTTLS or plain) cannot work."""
    if port == 993:
        return [_step("config", "imap", PASSED, "Port 993 (TLS implicite) : cohérent avec le lecteur.")]
    return [
        _step(
            "config",
            "imap",
            FAILED,
            f"Le lecteur IMAP n'utilise que TLS implicite (port 993) ; le port {port} ne fonctionnera pas.",
        )
    ]


def cert_finding(scope: str, cert: Optional[dict[str, Any]], now: datetime) -> dict[str, str]:
    """The certificate the server presented (its chain and host name were already verified by the TLS handshake)."""
    if not cert or "notAfter" not in cert:
        return _step("tls", scope, WARNING, "Connexion TLS établie, mais le certificat n'a pas pu être lu.")
    expires = datetime.fromtimestamp(ssl.cert_time_to_seconds(cert["notAfter"]), tz=timezone.utc)
    days = (expires - now).days
    if days < 0:
        return _step("tls", scope, FAILED, f"Le certificat du serveur a expiré il y a {-days} jour(s).")
    if days <= CERT_WARN_DAYS:
        return _step("tls", scope, WARNING, f"Certificat valide, mais il expire dans {days} jour(s).")
    return _step("tls", scope, PASSED, f"Certificat de confiance, nom d'hôte vérifié, valable encore {days} jour(s).")


def spf_finding(records: list[str]) -> dict[str, str]:
    spf = [r for r in records if r.lower().startswith("v=spf1")]
    if not spf:
        return _step(
            "spf",
            "sender",
            WARNING,
            "Aucun enregistrement SPF : les serveurs destinataires risquent de classer vos messages en spam.",
        )
    if len(spf) > 1:
        return _step(
            "spf", "sender", FAILED, "Plusieurs enregistrements SPF : c'est invalide, aucun n'est pris en compte."
        )
    return _step(
        "spf", "sender", PASSED, "Un enregistrement SPF est publié (sa présence ne garantit pas la délivrabilité)."
    )


def dmarc_finding(records: list[str]) -> dict[str, str]:
    dmarc = [r for r in records if r.lower().startswith("v=dmarc1")]
    if not dmarc:
        return _step("dmarc", "sender", WARNING, "Aucun enregistrement DMARC publié pour ce domaine.")
    policy = next((p.split("=", 1)[1] for p in dmarc[0].replace(" ", "").split(";") if p.lower().startswith("p=")), "?")
    return _step("dmarc", "sender", PASSED, f"DMARC publié (politique « {policy} »).")


def dkim_finding(found: list[str], tried: tuple[str, ...]) -> dict[str, str]:
    if found:
        return _step("dkim", "sender", PASSED, f"Clé DKIM trouvée (sélecteur {found[0]}).")
    return _step(
        "dkim",
        "sender",
        WARNING,
        "Aucune clé DKIM trouvée sous les sélecteurs courants de l'hébergeur ("
        + ", ".join(tried)
        + "). Le sélecteur de votre fournisseur peut être différent : vérifiez dans son interface.",
    )


# ---------------------------------------------------------------------------------------------- DNS TXT, stdlib only
class DnsError(Exception):
    pass


def system_nameserver(path: str = "/etc/resolv.conf") -> Optional[str]:
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "nameserver" and ":" not in parts[1]:
                    return parts[1]
    except OSError:
        return None
    return None


def _encode_name(name: str) -> bytes:
    out = b""
    for label in name.strip(".").split("."):
        raw = label.encode("idna")
        if not 0 < len(raw) < 64:
            raise DnsError("invalid name")
        out += bytes([len(raw)]) + raw
    return out + b"\x00"


def _skip_name(packet: bytes, pos: int) -> int:
    while True:
        if pos >= len(packet):
            raise DnsError("truncated answer")
        length = packet[pos]
        if length == 0:
            return pos + 1
        if length & 0xC0 == 0xC0:  # a compression pointer ends the name
            return pos + 2
        pos += 1 + length


def parse_txt_answer(packet: bytes, query_id: int) -> list[str]:
    """TXT strings of a DNS answer; [] for a name that has none (NXDOMAIN or NODATA)."""
    if len(packet) < 12:
        raise DnsError("truncated answer")
    ident, flags, qd, an = struct.unpack("!HHHH", packet[:8])
    if ident != query_id:
        raise DnsError("answer to another question")
    rcode = flags & 0x0F
    if rcode == 3:
        return []
    if rcode != 0:
        raise DnsError(f"the resolver answered with error code {rcode}")
    pos = 12
    for _ in range(qd):
        pos = _skip_name(packet, pos) + 4
    texts: list[str] = []
    for _ in range(an):
        pos = _skip_name(packet, pos)
        if pos + 10 > len(packet):
            raise DnsError("truncated answer")
        rtype, _cls, _ttl, rdlen = struct.unpack("!HHIH", packet[pos : pos + 10])
        pos += 10
        rdata = packet[pos : pos + rdlen]
        pos += rdlen
        if rtype == 16:
            joined, i = b"", 0
            while i < len(rdata):
                size = rdata[i]
                joined += rdata[i + 1 : i + 1 + size]
                i += 1 + size
            texts.append(joined.decode("utf-8", "replace"))
    return texts


def txt_lookup(name: str, *, nameserver: Optional[str] = None, port: int = 53, timeout: float = 3.0) -> list[str]:
    """TXT records of `name` through the system resolver (UDP, then TCP when the answer was truncated)."""
    server = nameserver or system_nameserver()
    if server is None:
        raise DnsError("no DNS resolver is configured on this machine")
    query_id = int.from_bytes(os.urandom(2), "big")
    question = _encode_name(name) + struct.pack("!HH", 16, 1)
    packet = struct.pack("!HHHHHH", query_id, 0x0100, 1, 0, 0, 0) + question
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.settimeout(timeout)
            udp.sendto(packet, (server, port))
            answer, _ = udp.recvfrom(4096)
        if len(answer) >= 4 and answer[2] & 0x02:  # TC: too big for UDP, ask again over TCP
            with socket.create_connection((server, port), timeout=timeout) as tcp:
                tcp.sendall(struct.pack("!H", len(packet)) + packet)
                size = struct.unpack("!H", tcp.recv(2))[0]
                answer = b""
                while len(answer) < size:
                    chunk = tcp.recv(size - len(answer))
                    if not chunk:
                        raise DnsError("truncated answer")
                    answer += chunk
    except (OSError, struct.error) as exc:
        raise DnsError(f"the DNS query failed ({type(exc).__name__})") from exc
    return parse_txt_answer(answer, query_id)


# ---------------------------------------------------------------------------------------------- the run
def _tls_certificate(host: str, port: int, mode: str, timeout: float = 10.0) -> Optional[dict[str, Any]]:
    """Open the connection the way the mail client does and return the verified peer certificate."""
    context = ssl.create_default_context()  # chain and host name verified: a failure raises ssl.SSLError
    if mode == "ssl":
        with socket.create_connection((host, port), timeout=timeout) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                return tls.getpeercert()
    import smtplib

    client = smtplib.SMTP(host, port, timeout=timeout)
    try:
        client.ehlo()
        client.starttls(context=context)
        return client.sock.getpeercert() if client.sock is not None else None  # type: ignore[union-attr]
    finally:
        try:
            client.quit()
        except Exception:  # noqa: BLE001 (closing is best effort: nothing was sent)
            client.close()


def _connection_steps(
    scope: str,
    host: str,
    port: int,
    mode: str,
    now: datetime,
    resolve: Callable[[str], Any],
    tls: Callable[[str, int, str], Optional[dict[str, Any]]],
) -> list[dict[str, str]]:
    try:
        resolve(host)
    except OSError as exc:
        return [
            _step(
                "dns",
                scope,
                FAILED,
                f"Le nom du serveur ne se résout pas ({type(exc).__name__}) : vérifiez l'orthographe.",
            )
        ]
    steps = [_step("dns", scope, PASSED, "Le nom du serveur se résout.")]
    try:
        steps.append(cert_finding(scope, tls(host, port, mode), now))
    except ssl.SSLError:
        steps.append(
            _step(
                "tls",
                scope,
                FAILED,
                "Erreur TLS : certificat non reconnu ou nom d'hôte différent de celui du certificat.",
            )
        )
    except OSError as exc:
        steps.append(
            _step(
                "tls",
                scope,
                FAILED,
                f"Connexion impossible au port {port} ({type(exc).__name__}) : port fermé, bloqué ou mauvais mode.",
            )
        )
    return steps


def _sign_in(scope: str, answer: dict[str, Any]) -> dict[str, str]:
    if answer.get("ok"):
        done = (
            "Authentification acceptée ; rien n'a été envoyé."
            if scope == "smtp"
            else "Connecté ; dossier ouvert en lecture seule, aucun message touché."
        )
        return _step("auth" if scope == "smtp" else "folder", scope, PASSED, done)
    return _step(
        "auth" if scope == "smtp" else "folder",
        scope,
        FAILED,
        f"{answer.get('error')} (étape : {answer.get('phase')}).",
    )


def run(
    *,
    now: Optional[datetime] = None,
    smtp_config: Optional[smtp_svc.SmtpConfig] = None,
    imap_config: Optional[imap_svc.ImapConfig] = None,
    sender_email: Optional[str] = None,
    resolve: Callable[[str], Any] = socket.getaddrinfo,
    tls: Callable[[str, int, str], Optional[dict[str, Any]]] = _tls_certificate,
    smtp_check: Callable[..., dict[str, Any]] = smtp_svc.check_connection,
    imap_check: Callable[..., dict[str, Any]] = imap_svc.check_connection,
    txt: Callable[[str], list[str]] = txt_lookup,
) -> dict[str, Any]:
    """Every step in order; a step that cannot run says why. Never raises, never sends, never returns a credential."""
    moment = now or datetime.now(timezone.utc)
    started = time.monotonic()
    steps: list[dict[str, str]] = []

    if smtp_config is None:
        steps.append(_step("config", "smtp", SKIPPED, "SMTP non configuré (SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD)."))
    else:
        steps += smtp_findings(smtp_config.host, smtp_config.port, smtp_config.security)
        steps += _connection_steps(
            "smtp", smtp_config.host, smtp_config.port, smtp_config.security, moment, resolve, tls
        )
        reached_tls = any(s["scope"] == "smtp" and s["id"] == "tls" and s["status"] != FAILED for s in steps)
        steps.append(
            _sign_in("smtp", smtp_check(smtp_config))
            if reached_tls
            else _step("auth", "smtp", SKIPPED, "Non testée : la connexion TLS n'aboutit pas.")
        )

    if imap_config is None:
        steps.append(
            _step("config", "imap", SKIPPED, "IMAP non configuré : les réponses et oppositions ne sont pas lues.")
        )
    else:
        steps += imap_findings(imap_config.host, imap_config.port)
        steps += _connection_steps("imap", imap_config.host, imap_config.port, "ssl", moment, resolve, tls)
        reached_tls = any(s["scope"] == "imap" and s["id"] == "tls" and s["status"] != FAILED for s in steps)
        steps.append(
            _sign_in("imap", imap_check(imap_config))
            if reached_tls
            else _step("folder", "imap", SKIPPED, "Non testé : la connexion TLS n'aboutit pas.")
        )

    domain = (sender_email or "").rsplit("@", 1)[-1].strip().lower() if sender_email and "@" in sender_email else ""
    if not domain:
        steps.append(
            _step("spf", "sender", SKIPPED, "Adresse d'expéditeur absente (OUTREACH_SENDER_EMAIL) : DNS non vérifié.")
        )
    else:
        try:
            steps.append(spf_finding(txt(domain)))
            steps.append(dmarc_finding(txt(f"_dmarc.{domain}")))
            found = [sel for sel in DKIM_SELECTORS if any("p=" in r for r in txt(f"{sel}._domainkey.{domain}"))]
            steps.append(dkim_finding(found, DKIM_SELECTORS))
        except DnsError as exc:
            steps.append(_step("spf", "sender", SKIPPED, f"DNS non vérifié : {exc}."))

    failed = [s for s in steps if s["status"] == FAILED]
    return {
        "checked_at": moment,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "steps": steps,
        "ok": not failed,
        "failed": len(failed),
        "warnings": len([s for s in steps if s["status"] == WARNING]),
        "notes": [
            "Aucun message n'a été envoyé : l'authentification SMTP s'arrête avant MAIL FROM, le dossier IMAP est "
            "ouvert en lecture seule.",
            "SPF, DKIM et DMARC sont des prérequis : leur présence ne garantit pas la délivrabilité.",
        ],
    }
