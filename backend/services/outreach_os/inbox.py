"""Classify one inbound e-mail from the sending mailbox: a reply, a hard bounce, or noise. Pure: no I/O, no clock.

Rules (nothing is concluded from what is not there):
- A bounce is only `hard` when the delivery report says so (action `failed`, status 5.x.x). A temporary failure (4.x.x),
  an unreadable report or an auto-responder is `ignore`: the address is never suppressed on a guess.
- A reply must reference one of our messages (In-Reply-To / References). Auto-replies (out of office) are `ignore`.
- The excerpt is the reader's own text only (quoted lines dropped), capped; the full message is never kept.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from email import message_from_bytes, policy
from email.message import EmailMessage, Message
from email.utils import parseaddr
from typing import Literal, Optional

from services.outreach_os.normalize import normalize_email
from services.outreach_os.replies import is_opt_out

EXCERPT_CHARS = 500
_MSGID = re.compile(r"<([^<>\s]+)>")
_AUTO_SUBJECT = re.compile(
    r"out of office|absence du bureau|réponse automatique|reponse automatique|automatic reply", re.I
)
_DAEMON = re.compile(r"mailer-daemon|postmaster", re.I)

Kind = Literal["reply", "hard_bounce", "ignore"]


@dataclass(frozen=True)
class InboundItem:
    kind: Kind
    inbound_id: str  # Message-ID of this inbound message (dedup key); "" when absent
    references: list[str] = field(default_factory=list)  # our Message-IDs it points at (angle brackets stripped)
    failed_recipient: Optional[str] = None  # bounces only
    excerpt: str = ""  # replies only
    opt_out: bool = False
    sender: Optional[str] = None  # normalised From address, replies only


def _ids(value: str | None) -> list[str]:
    return _MSGID.findall(value or "")


def _is_auto(msg: Message) -> bool:
    auto = (msg.get("Auto-Submitted") or "no").strip().lower()
    precedence = (msg.get("Precedence") or "").strip().lower()
    return (
        auto != "no"
        or precedence in {"bulk", "junk", "auto_reply"}
        or bool(msg.get("X-Autoreply") or msg.get("X-Autorespond"))
        or bool(_AUTO_SUBJECT.search(msg.get("Subject") or ""))
    )


def _own_text(msg: EmailMessage) -> str:
    part = msg.get_body(preferencelist=("plain",))
    raw = part.get_content() if part is not None else ""
    kept: list[str] = []
    for line in str(raw).splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            continue
        if re.match(r"^(le .+ a écrit|on .+ wrote)\s*:?\s*$", stripped, re.I) or stripped.startswith("-----Original"):
            break  # everything below is the quoted thread
        kept.append(line)
    return re.sub(r"\s+", " ", " ".join(kept)).strip()[:EXCERPT_CHARS]


def _delivery_status(msg: EmailMessage) -> tuple[Optional[str], Optional[str]]:
    """(failed recipient, status code) from the message/delivery-status part, if there is one."""
    for part in msg.walk():
        if part.get_content_type() != "message/delivery-status":
            continue
        recipient = status = action = None
        for block in part.get_payload():
            if not isinstance(block, Message):
                continue
            if block.get("Final-Recipient"):
                recipient = str(block.get("Final-Recipient")).split(";", 1)[-1].strip()
                status = str(block.get("Status") or "").strip()
                action = str(block.get("Action") or "").strip().lower()
        if recipient and action == "failed" and re.match(r"^5\.\d+\.\d+$", status or ""):
            return normalize_email(recipient), status
        return None, status
    return None, None


def _original_ids(msg: EmailMessage) -> list[str]:
    found: list[str] = []
    for part in msg.walk():
        if part.get_content_type() in ("message/rfc822", "text/rfc822-headers"):
            payload = part.get_payload()
            blocks = payload if isinstance(payload, list) else [payload]
            for block in blocks:
                if isinstance(block, Message):
                    found += _ids(block.get("Message-ID"))
                elif isinstance(block, str):
                    found += _ids(next((ln for ln in block.splitlines() if ln.lower().startswith("message-id:")), ""))
    return found


def classify(raw: bytes) -> InboundItem:
    msg = message_from_bytes(raw, policy=policy.default)
    assert isinstance(msg, EmailMessage)
    inbound_id = (_ids(msg.get("Message-ID")) or [""])[0]
    sender = str(msg.get("From") or "")
    is_report = msg.get_content_type() == "multipart/report" or bool(_DAEMON.search(sender))
    if is_report:
        recipient, _ = _delivery_status(msg)
        if recipient is None:
            return InboundItem("ignore", inbound_id)
        return InboundItem("hard_bounce", inbound_id, _original_ids(msg), failed_recipient=recipient)
    refs = _ids(msg.get("In-Reply-To")) + _ids(msg.get("References"))
    if not refs or _is_auto(msg):
        return InboundItem("ignore", inbound_id)
    excerpt = _own_text(msg)
    return InboundItem(
        "reply",
        inbound_id,
        refs,
        excerpt=excerpt,
        opt_out=is_opt_out(excerpt),
        sender=normalize_email(parseaddr(sender)[1]),
    )
