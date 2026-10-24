"""Reviewer dismissal of a wrong signal and campaign rescoring, on a running server (fixtures, no network)."""

import os
import uuid

import pytest
import requests
from helpers import unique_email

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"


def _register():
    uid = uuid.uuid4().hex[:10]
    token = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"sr_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "R",
            "organization_name": f"R {uid}",
        },
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def org():
    h = _register()
    assert requests.post(f"{API}/prospects/discovery/run", headers=h, json={}).status_code == 200
    return h


def _prospect(h, name="La Table d'Alice"):
    items = requests.get(f"{API}/prospects", headers=h, params={"limit": 200}).json()["items"]
    return next(p["id"] for p in items if p["name"] == name)


def _detail(h, pid):
    return requests.get(f"{API}/prospects/{pid}", headers=h).json()


def _detected(detail):
    return next(s for s in detail["signals"] if s["state"] == "detected")


def _dismiss(h, pid, key, reason="This is wrong: the restaurant does take bookings"):
    return requests.post(f"{API}/prospects/{pid}/signals/{key}/dismiss", headers=h, json={"reason": reason})


def test_a_dismissed_signal_reads_as_unknown_and_the_score_follows(org):
    pid = _prospect(org)
    before = _detail(org, pid)
    signal = _detected(before)
    resp = _dismiss(org, pid, signal["key"])
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["signal"]["state"] == "unknown" and out["signal"]["dismissed"] is True
    assert out["signal"]["observed_state"] == "detected" and "wrong" in out["signal"]["dismissed_reason"]
    after = _detail(org, pid)
    assert after["score"] <= before["score"] and after["score_detail"]["version"] == before["score_detail"]["version"]
    shown = next(s for s in after["signals"] if s["key"] == signal["key"])
    assert shown["dismissed"] is True and shown["state"] == "unknown" and shown["evidence"] == signal["evidence"]
    line = next(ln for ln in after["score_detail"]["breakdown"] if ln["signal"] == signal["key"])
    assert line["points"] == 0 and line["state"] == "unknown"
    assert "Dismissed by a reviewer" in line["explanation"] and "Observed: detected" in line["explanation"]


def test_a_draft_never_states_a_dismissed_signal(org):
    pid = _prospect(org)
    requests.post(f"{API}/prospects/{pid}/review", headers=org, json={"decision": "approve"})
    first = requests.post(f"{API}/prospects/{pid}/drafts", headers=org).json()
    assert "réserver en ligne" in first["body"]
    assert _dismiss(org, pid, "booking_page_missing").status_code == 200
    second = requests.post(f"{API}/prospects/{pid}/drafts", headers={**org, "Idempotency-Key": uuid.uuid4().hex}).json()
    assert "réserver en ligne" not in second["body"] and not any("réserv" in f for f in second["facts"])


def test_dismiss_and_restore_are_guarded_audited_and_reversible(org):
    pid = _prospect(org)
    key = _detected(_detail(org, pid))["key"]
    assert _dismiss(org, pid, key, reason="no").status_code == 422  # a reason is required
    assert (
        requests.post(
            f"{API}/prospects/{pid}/signals/nope/dismiss", headers=org, json={"reason": "valid reason"}
        ).status_code
        == 404
    )
    assert (
        requests.post(f"{API}/prospects/{pid}/signals/{key}/restore", headers=org).status_code == 409
    )  # nothing to restore
    assert _dismiss(org, pid, key).status_code == 200
    assert _dismiss(org, pid, key).status_code == 409  # already dismissed
    restored = requests.post(f"{API}/prospects/{pid}/signals/{key}/restore", headers=org)
    assert (
        restored.status_code == 200
        and restored.json()["signal"]["state"] == "detected"
        and restored.json()["signal"]["dismissed"] is False
    )
    actions = [e["action"] for e in requests.get(f"{API}/prospects/{pid}/events", headers=org).json()]
    assert "signal.dismissed" in actions and "signal.restored" in actions
    assert "valid reason" not in str(
        requests.get(f"{API}/prospects/{pid}/events", headers=org).json()
    )  # the text is not copied to the log


def test_a_rediscovery_keeps_the_dismissal(org):
    pid = _prospect(org)
    key = _detected(_detail(org, pid))["key"]
    assert _dismiss(org, pid, key).status_code == 200
    assert requests.post(f"{API}/prospects/discovery/run", headers=org, json={}).status_code == 200
    again = next(s for s in _detail(org, pid)["signals"] if s["key"] == key)
    assert again["dismissed"] is True and again["state"] == "unknown"


def test_dismissals_are_per_organisation_and_need_a_login(org):
    pid = _prospect(org)
    key = _detected(_detail(org, pid))["key"]
    other = _register()
    assert _dismiss(other, pid, key).status_code == 404
    assert requests.post(
        f"{API}/prospects/{pid}/signals/{key}/dismiss", json={"reason": "valid reason"}
    ).status_code in (401, 403)


# ---------------------------------------------------------------- campaign rescoring
def _campaign_with(h, lead_ids):
    step = {"channel": "email", "delay_hours": 0, "subject": "Hello", "body": "Hi", "language": "en"}
    cid = requests.post(f"{API}/campaigns", headers=h, json={"name": "Rescore", "steps": [step]}).json()["id"]
    assert (
        requests.post(f"{API}/campaigns/{cid}/assign-leads", headers=h, json={"lead_ids": lead_ids}).status_code == 200
    )
    return cid


def test_a_campaign_rescore_covers_its_leads_and_is_rate_limited(org):
    """CRM leads over HTTP. (A discovery prospect only joins a campaign when live sending is on; its path is the same
    `rescore_lead` the single-prospect endpoint uses, covered above.)"""
    leads = [
        requests.post(f"{API}/leads", headers=org, json={"full_name": f"L{i}", "email": unique_email("c")}).json()["id"]
        for i in range(2)
    ]
    cid = _campaign_with(org, leads)
    resp = requests.post(f"{API}/campaigns/{cid}/rescore", headers=org)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"total": 2, "prospects_rescored": 0, "crm_leads_rescored": 2, "skipped": 0}
    for _ in range(2):
        assert requests.post(f"{API}/campaigns/{cid}/rescore", headers=org).status_code == 200
    limited = requests.post(f"{API}/campaigns/{cid}/rescore", headers=org)
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1


def test_a_campaign_rescore_is_scoped_to_its_organisation(org):
    cid = _campaign_with(
        org,
        [requests.post(f"{API}/leads", headers=org, json={"full_name": "L", "email": unique_email("d")}).json()["id"]],
    )
    assert requests.post(f"{API}/campaigns/{cid}/rescore", headers=_register()).status_code == 404
    assert requests.post(f"{API}/campaigns/{uuid.uuid4()}/rescore", headers=org).status_code == 404
    assert requests.post(f"{API}/campaigns/{cid}/rescore").status_code in (401, 403)
