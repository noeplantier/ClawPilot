"""Signed unsubscribe tokens: unforgeable, stateless, reusable (opting out twice is harmless)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid


def _sign(secret: str, payload: str) -> str:
    key = hashlib.sha256(f"unsubscribe:{secret}".encode()).digest()  # derived key: the JWT secret is never used raw
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()[:32]


def make_token(secret: str, account_id: uuid.UUID, lead_id: uuid.UUID) -> str:
    payload = f"{account_id}.{lead_id}"
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=") + "." + _sign(secret, payload)


def parse_token(secret: str, token: str) -> tuple[uuid.UUID, uuid.UUID] | None:
    """Return (account_id, lead_id) if the token is authentic, else None."""
    try:
        encoded, signature = token.rsplit(".", 1)
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
        if not hmac.compare_digest(signature, _sign(secret, payload)):
            return None
        account, lead = payload.split(".")
        return uuid.UUID(account), uuid.UUID(lead)
    except (ValueError, UnicodeDecodeError):
        return None
