"""Dashboard overview: every figure is computed from stored rows, and "nothing yet" is null, not zero."""

import os
import uuid

import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"


def _org():
    uid = uuid.uuid4().hex[:10]
    resp = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"dash_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Dash Tester",
            "organization_name": f"Dash Org {uid}",
        },
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _overview(h):
    resp = requests.get(f"{API}/dashboard/overview", headers=h)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _approved_draft(h, name):
    items = requests.get(f"{API}/prospects", headers=h, params={"limit": 200}).json()["items"]
    pid = next(p["id"] for p in items if p["name"] == name)
    requests.post(f"{API}/prospects/{pid}/review", headers=h, json={"decision": "approve"})
    did = requests.post(f"{API}/prospects/{pid}/drafts", headers=h).json()["id"]
    requests.post(f"{API}/prospects/drafts/{did}/review", headers=h, json={"decision": "approve"})
    return pid, did


def test_requires_authentication():
    assert requests.get(f"{API}/dashboard/overview").status_code == 401


def test_a_new_organisation_gets_explicit_empty_values_not_invented_zeros():
    d = _overview(_org())
    k = d["kpis"]
    assert (k["prospects"], k["messages"], k["replies"], k["bounces"], k["unsubscribed"], k["sent_today"]) == (0,) * 6
    assert k["avg_score"] is None and k["reply_rate"] is None and k["bounce_rate"] is None
    assert d["latest_prospects"] == [] and d["latest_signals"] == [] and d["campaigns"] == [] and d["inbox"] == []
    assert d["top_signals"] == []
    assert d["geography"]["total"] == 0 and d["geography"]["countries"] == [] and d["geography"]["unknown_country"] == 0
    assert len(d["series"]) == 14 and all(p["sent"] == 0 and p["replied"] == 0 for p in d["series"])
    lim = d["limits"]
    assert lim["dry_run"] is True and lim["kill_switch"] is False and lim["paused"] is False
    assert lim["remaining_today"] == lim["max_per_day"] and lim["sandbox"] is True


def test_discovery_fills_prospects_scores_and_live_signals():
    h = _org()
    assert requests.post(f"{API}/prospects/discovery/run", headers=h, json={}).status_code == 200
    d = _overview(h)
    k = d["kpis"]
    assert k["prospects"] > 0 and k["pending_review"] == k["prospects"] and k["approved"] == 0
    assert k["scored"] > 0 and 0 <= k["avg_score"] <= 100
    assert d["latest_prospects"] and len(d["latest_prospects"]) <= 6
    assert d["latest_signals"], "the fixture directory has detected signals"
    first = d["latest_signals"][0]
    assert first["label"] and first["evidence"] and first["name"]  # provenance: what was observed, on whom
    top = d["top_signals"]
    assert top and all(t["label"] and t["prospects"] >= 1 for t in top)
    assert [t["prospects"] for t in top] == sorted((t["prospects"] for t in top), reverse=True)
    geo = d["geography"]
    assert geo["total"] == k["prospects"]
    assert sum(c["prospects"] for c in geo["countries"]) + geo["unknown_country"] == geo["total"]  # nothing invented


def test_top_signals_follow_a_reviewer_dismissal():
    h = _org()
    requests.post(f"{API}/prospects/discovery/run", headers=h, json={})
    before = {t["key"]: t["prospects"] for t in _overview(h)["top_signals"]}
    key = next(iter(before))
    items = requests.get(f"{API}/prospects", headers=h, params={"limit": 200}).json()["items"]
    target = None
    for item in items:
        detail = requests.get(f"{API}/prospects/{item['id']}", headers=h).json()
        if any(s["key"] == key and s["state"] == "detected" for s in detail["signals"]):
            target = item["id"]
            break
    assert target
    done = requests.post(
        f"{API}/prospects/{target}/signals/{key}/dismiss", headers=h, json={"reason": "Checked by hand: it is wrong"}
    )
    assert done.status_code == 200, done.text
    after = {t["key"]: t["prospects"] for t in _overview(h)["top_signals"]}
    assert after.get(key, 0) == before[key] - 1  # a dismissed signal reads as unknown: it no longer counts


def test_dispatch_reply_bounce_and_unsubscribe_show_up_with_real_rates():
    h = _org()
    requests.post(f"{API}/prospects/discovery/run", headers=h, json={})
    requests.put(f"{API}/outbound/limits", headers=h, json={"min_delay_seconds": 0})
    _, d1 = _approved_draft(h, "La Table d'Alice")
    _, d2 = _approved_draft(h, "Chez Marcel")
    m1 = requests.post(f"{API}/outbound/dispatch", headers=h, json={"draft_id": d1}).json()
    m2 = requests.post(f"{API}/outbound/dispatch", headers=h, json={"draft_id": d2}).json()

    k = _overview(h)["kpis"]
    assert k["messages"] == 2 and k["sent_today"] == 2 and k["replies"] == 0
    assert k["reply_rate"] == 0.0  # something was sent and nobody replied: a real 0, unlike "nothing sent"

    requests.post(
        f"{API}/outbound/{m1['id']}/simulate", headers=h, json={"event": "replied", "text": "Intéressé, appelez-moi"}
    )
    requests.post(f"{API}/outbound/{m2['id']}/simulate", headers=h, json={"event": "bounced"})
    d = _overview(h)
    k = d["kpis"]
    assert (k["replies"], k["bounces"]) == (1, 1) and k["reply_rate"] == 0.5 and k["bounce_rate"] == 0.5
    assert d["inbox"][0]["excerpt"] == "Intéressé, appelez-moi" and d["inbox"][0]["simulated"] is True
    today = d["series"][-1]
    assert today["sent"] == 2 and today["replied"] == 1

    # A STOP reply opts the prospect out: the counter follows.
    m3_body = requests.get(f"{API}/outbound/{m1['id']}", headers=h).json()
    assert m3_body["status"] in ("replied", "sent")
    requests.post(f"{API}/outbound/{m1['id']}/simulate", headers=h, json={"event": "replied", "text": "STOP"})
    assert _overview(h)["kpis"]["unsubscribed"] >= 1
    assert d["limits"]["remaining_today"] == d["limits"]["max_per_day"] - 2


def test_organisations_never_see_each_others_numbers():
    a, b = _org(), _org()
    requests.post(f"{API}/prospects/discovery/run", headers=a, json={})
    assert _overview(a)["kpis"]["prospects"] > 0
    assert _overview(b)["kpis"]["prospects"] == 0 and _overview(b)["latest_signals"] == []


def test_campaign_health_rates_are_null_until_something_is_sent():
    h = _org()
    step = {"channel": "email", "delay_hours": 0, "subject": "s", "body": "b", "language": "en"}
    requests.post(f"{API}/campaigns", headers=h, json={"name": "Health", "steps": [step]})
    row = _overview(h)["campaigns"][0]
    assert row["name"] == "Health" and row["sent"] == 0 and row["open_rate"] is None and row["reply_rate"] is None
