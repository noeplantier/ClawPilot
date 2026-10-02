"""SMTP e-mail adapter (stdlib `smtplib`): the real channel behind `ChannelAdapter`.

Nothing here runs unless `FEATURE_LIVE_SENDING` is on and every `SMTP_*` variable below is set; otherwise
`adapter_from_env()` returns None and dispatch refuses (fail closed). Rules:

- TLS is mandatory (STARTTLS or implicit SSL) with certificate and hostname verification. There is no plain option
  and no fallback if the server does not offer STARTTLS.
- Timeouts on every socket operation. The call blocks, so dispatch runs it in a worker thread.
- The password is never logged, returned, or part of `repr`; error texts are classified and redacted.
- A refusal before the message was accepted is `failed`. A network error after the recipient/data phase began, where we
  cannot know whether the server accepted the message, is `unknown`: the caller keeps the message in `sending` and never
  retries it by itself (at most once beats a duplicate cold e-mail).
- While the sandbox is on, any recipient outside the allowlist is refused here too (dispatch checks first).

    SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD   required
    SMTP_SECURITY                             starttls (default, port 587) | ssl (port 465)
    SMTP_PORT                                 optional, defaults from the security mode
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Optional

from services import feature_flags
from services.outreach_os import sandbox
from services.outreach_os.channels import ChannelMessage, SendResult
from services.outreach_os.normalize import normalize_email

logger = logging.getLogger(__name__)

SECURITY_MODES = {"starttls": 587, "ssl": 465}
TIMEOUT_SECONDS = 20.0
MAX_ERROR_CHARS = 160


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str = field(repr=False)
    security: str = "starttls"
    timeout: float = TIMEOUT_SECONDS

    @classmethod
    def from_env(cls) -> Optional["SmtpConfig"]:
        """None unless host, username and password are set and the settings are valid (never a partial default)."""
        host = os.environ.get("SMTP_HOST", "").strip()
        username = os.environ.get("SMTP_USERNAME", "").strip()
        password = os.environ.get("SMTP_PASSWORD", "")
        security = os.environ.get("SMTP_SECURITY", "").strip().lower() or "starttls"
        if not host or not username or not password or security not in SECURITY_MODES:
            return None
        raw_port = os.environ.get("SMTP_PORT", "").strip()
        try:
            port = int(raw_port) if raw_port else SECURITY_MODES[security]
        except ValueError:
            return None
        if not 0 < port < 65536:
            return None
        return cls(host=host, port=port, username=username, password=password, security=security)


def is_configured() -> bool:
    return SmtpConfig.from_env() is not None


def status() -> dict:
    """What Settings may show: never the username or the password."""
    config = SmtpConfig.from_env()
    return {
        "configured": config is not None,
        "host": config.host if config else None,
        "security": config.security if config else None,
    }


def _one_line(value: str) -> str:
    """Headers cannot carry line breaks: a CR/LF in a subject would otherwise inject headers."""
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())


def build_message(message: ChannelMessage, *, now: Optional[datetime] = None) -> EmailMessage:
    """The RFC 5322 message: identity in From, plain text (quoted-printable, 7-bit safe), List-Unsubscribe headers."""
    sender = normalize_email(message.sender_email)
    recipient = normalize_email(message.to)
    if sender is None or recipient is None:
        raise ValueError("invalid sender or recipient address")
    msg = EmailMessage()
    msg["From"] = formataddr((_one_line(message.sender_name), sender))
    msg["To"] = recipient
    msg["Reply-To"] = sender
    msg["Subject"] = _one_line(message.subject)
    msg["Date"] = formatdate(timeval=now.timestamp() if now else None, localtime=False, usegmt=True)
    msg["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[1])
    for name, value in message.headers.items():
        msg[_one_line(name)] = _one_line(value)
    msg.set_content(message.body, charset="utf-8", cte="quoted-printable")
    return msg


def _reply_text(exc: smtplib.SMTPResponseException, secrets: tuple[str, ...]) -> str:
    raw = exc.smtp_error.decode("utf-8", "replace") if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error)
    return _redact(" ".join(raw.split()), secrets)[:MAX_ERROR_CHARS]


def _redact(text: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


class SmtpEmailAdapter:
    """Sends one message over an authenticated, verified TLS connection. Implements `ChannelAdapter`."""

    channel = "email"
    name = "smtp"
    dry_run = False

    def __init__(self, config: SmtpConfig, allowlist: Optional[tuple[str, ...]] = None) -> None:
        self._config = config
        self._allowlist = allowlist  # None = sandbox off; a tuple (possibly empty) = only these recipients

    def send(self, message: ChannelMessage) -> SendResult:
        recipient = normalize_email(message.to)
        if recipient is None:
            return SendResult("failed", None, "invalid recipient address", simulated=False)
        if self._allowlist is not None and not sandbox.is_allowed(recipient, self._allowlist):
            return SendResult("failed", None, "recipient is not on the sandbox allowlist", simulated=False)
        if not message.subject.strip() or not message.body.strip():
            return SendResult("failed", None, "empty subject or body", simulated=False)
        if "List-Unsubscribe" not in message.headers:
            return SendResult("failed", None, "missing List-Unsubscribe header", simulated=False)
        try:
            msg = build_message(message)
        except ValueError as exc:
            return SendResult("failed", None, str(exc), simulated=False)
        return self._deliver(msg, from_addr=normalize_email(message.sender_email) or "", to_addr=recipient)

    def _deliver(self, msg: EmailMessage, *, from_addr: str, to_addr: str) -> SendResult:
        cfg = self._config
        secrets = (cfg.password,)
        phase = "connect"
        client: Optional[smtplib.SMTP] = None
        try:
            context = ssl.create_default_context()  # verifies the certificate chain and the host name
            if cfg.security == "ssl":
                client = smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=cfg.timeout, context=context)
            else:
                client = smtplib.SMTP(cfg.host, cfg.port, timeout=cfg.timeout)
                client.ehlo()
                phase = "starttls"
                client.starttls(context=context)  # raises if the server does not offer it: never falls back to plain
                client.ehlo()
            phase = "login"
            client.login(cfg.username, cfg.password)
            phase = "send"
            client.send_message(msg, from_addr=from_addr, to_addrs=[to_addr])
        except smtplib.SMTPAuthenticationError as exc:
            return self._failed(f"authentication failed ({exc.smtp_code}): {_reply_text(exc, secrets)}")
        except smtplib.SMTPRecipientsRefused:
            return self._failed("the server refused the recipient address")
        except smtplib.SMTPSenderRefused as exc:
            return self._failed(f"the server refused the sender ({exc.smtp_code}): {_reply_text(exc, secrets)}")
        except smtplib.SMTPResponseException as exc:
            return self._failed(f"the server replied {exc.smtp_code}: {_reply_text(exc, secrets)}")
        except ssl.SSLError:
            return self._failed("TLS error: certificate not trusted or host name mismatch")
        except (smtplib.SMTPException, OSError) as exc:
            if phase == "send":
                logger.warning("smtp outcome unknown (%s)", type(exc).__name__)
                return SendResult(
                    "unknown", None, f"connection lost while sending ({type(exc).__name__}): outcome unknown", False
                )
            return self._failed(f"{phase} failed ({type(exc).__name__})")
        finally:
            if client is not None:
                try:
                    client.quit()
                except Exception:  # the message was already accepted or refused: closing is best effort
                    client.close()
        logger.info("smtp message accepted for %s", to_addr.rsplit("@", 1)[1])
        return SendResult("sent", str(msg["Message-ID"]).strip("<>"), simulated=False)

    @staticmethod
    def _failed(error: str) -> SendResult:
        logger.warning("smtp send refused: %s", error)
        return SendResult("failed", None, error, simulated=False)


def adapter_from_env(extra_allowed: tuple[str, ...] = ()) -> Optional[SmtpEmailAdapter]:
    """The configured adapter, or None. While the sandbox is on it only writes to the allowlist (+ `extra_allowed`)."""
    config = SmtpConfig.from_env()
    if config is None:
        return None
    return SmtpEmailAdapter(
        config, (*feature_flags.live_allowlist(), *extra_allowed) if feature_flags.sandbox() else None
    )
