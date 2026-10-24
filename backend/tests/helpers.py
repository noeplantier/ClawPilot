"""Shared helpers for the HTTP integration tests (they talk to a running server, never to a real provider)."""

import os
import uuid

import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

OPEN_LIMITS = {"max_per_day": 100000, "max_per_hour": 100000, "min_delay_seconds": 0, "sending_paused": False}


def open_send_limits(headers: dict, base_url: str = BASE_URL) -> None:
    """Lift the send limits and the pause for the test organisation, on both channels.

    The legacy suites send many messages in a row from the same organisation; the default policy (20/day, 60 s between
    sends) would legitimately refuse them. Tests of the limits themselves set their own values on a separate account.
    """
    for channel in ("email", "whatsapp"):
        response = requests.put(
            f"{base_url}/api/outbound/limits", params={"channel": channel}, headers=headers, json=OPEN_LIMITS
        )
        assert response.status_code == 200, response.text


def unique_email(prefix: str = "t") -> str:
    """A fresh address on a reserved domain (RFC 2606), so a test can be replayed on a database already used."""
    return f"{prefix}_{uuid.uuid4().hex[:10]}@test.example"
