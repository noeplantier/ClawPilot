"""The AI status shown in Settings must reflect what the composer will really do."""

import importlib.util

import pytest

from services import ai_svc


def _library(monkeypatch, present):
    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a, **k: (
            object()
            if name == "emergentintegrations" and present
            else (None if name == "emergentintegrations" else real(name, *a, **k))
        ),
    )


@pytest.mark.parametrize(
    "key,library,active,mode,reason",
    [
        (None, False, False, "template", "EMERGENT_LLM_KEY is not set"),
        ("", True, False, "template", "EMERGENT_LLM_KEY is not set"),
        ("k", False, False, "template", "the emergentintegrations package is not installed"),
        ("k", True, True, "live", None),
    ],
)
def test_status_matches_what_generate_message_will_do(monkeypatch, key, library, active, mode, reason):
    monkeypatch.setattr(ai_svc, "EMERGENT_KEY", key)
    _library(monkeypatch, library)
    s = ai_svc.status()
    assert (s["active"], s["mode"], s["reason"]) == (active, mode, reason)
    assert s["key_configured"] is bool(key) and s["library_available"] is library


def test_status_never_exposes_the_key(monkeypatch):
    monkeypatch.setattr(ai_svc, "EMERGENT_KEY", "super-secret-value")
    assert "super-secret-value" not in str(ai_svc.status())
