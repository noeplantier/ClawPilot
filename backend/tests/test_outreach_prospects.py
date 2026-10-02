"""OutreachOS end-to-end on a running server: fixture discovery → dedupe → signals → score → human review →
draft → unsubscribe → erasure. Fully local (fixtures only), nothing is sent.

The server needs OUTREACH_SENDER_NAME/COMPANY/ADDRESS/EMAIL set (see .github/workflows/ci.yml).
"""

import os
import re
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"


def _register():
    uid = uuid.uuid4().hex[:10]
    resp = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"os_{uid}@test.com",
            "password": uuid.uuid4().hex,
            "full_name": "OS Tester",
            "organization_name": f"OS Org {uid}",
        },
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture()
def org():
    return _register()


def _run(h):
    resp = requests.post(f"{API}/prospects/discovery/run", headers=h, json={"source": "fixture_directory"})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _by_name(h, review_status=None):
    params = {"review_status": review_status} if review_status else {}
    resp = requests.get(f"{API}/prospects", headers=h, params={"limit": 200, **params})
    assert resp.status_code == 200, resp.text
    return {p["name"]: p for p in resp.json()["items"]}, resp.json()


def _detail(h, pid):
    resp = requests.get(f"{API}/prospects/{pid}", headers=h)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _review(h, pid, decision, note=None):
    return requests.post(f"{API}/prospects/{pid}/review", headers=h, json={"decision": decision, "note": note})


# ---------------------------------------------------------------------------------------------------------
def test_discovery_dedupes_and_is_idempotent(org):
    first = _run(org)
    assert first["dry_run"] is True
    assert (first["listings_found"], first["entities"], first["duplicates_merged"]) == (9, 7, 2)
    assert (first["prospects_created"], first["prospects_updated"], first["suppressed"]) == (7, 0, 0)

    prospects, body = _by_name(org)
    assert body["total"] == 7
    assert {"Chez Marcel", "Sushi Kaze", "La Table d'Alice", "Le Petit Bouchon"} <= set(prospects)
    assert not any("SARL" in name or name.isupper() for name in prospects)  # merged variants did not leak

    second = _run(org)
    assert (second["prospects_created"], second["prospects_updated"]) == (0, 7)
    assert (second["sources_recorded"], second["signals_recorded"], second["scores_recorded"]) == (0, 0, 0)
    assert _by_name(org)[1]["total"] == 7


def test_list_is_sorted_by_score_and_filterable(org):
    _run(org)
    _, body = _by_name(org)
    scores = [p["score"] for p in body["items"]]
    assert all(isinstance(s, int) and 0 <= s <= 100 for s in scores)
    assert scores == sorted(scores, reverse=True)
    assert all(p["review_status"] == "pending" for p in body["items"])

    top = scores[0]
    only_top = requests.get(f"{API}/prospects", headers=org, params={"min_score": top}).json()
    assert only_top["total"] >= 1 and all(p["score"] >= top for p in only_top["items"])
    assert requests.get(f"{API}/prospects", headers=org, params={"review_status": "approved"}).json()["total"] == 0
    assert requests.get(f"{API}/prospects", headers=org, params={"review_status": "bogus"}).status_code == 422


def test_detail_shows_provenance_signals_and_explained_score(org):
    _run(org)
    prospects, _ = _by_name(org)

    marcel = _detail(org, prospects["Chez Marcel"]["id"])
    assert len(marcel["sources"]) == 2  # d-001 and the merged duplicate d-007
    assert {s["external_id"] for s in marcel["sources"]} == {"d-001", "d-007"}
    assert all(s["source_name"] == "fixture_directory" and s["license_note"] for s in marcel["sources"])

    bouchon = _detail(org, prospects["Le Petit Bouchon"]["id"])
    signals = {s["key"]: s for s in bouchon["signals"]}
    assert len(signals) == 7
    assert signals["no_website"]["state"] == "detected" and "No website listed" in signals["no_website"]["evidence"]
    assert signals["website_unreachable"]["state"] == "unknown"  # not applicable: never concluded from absence
    assert signals["booking_page_missing"]["state"] == "unknown"
    detail = bouchon["score_detail"]
    assert detail["version"] == 1 and detail["config_hash"] and 0 <= detail["coverage"] <= 1
    lines = {ln["signal"]: ln for ln in detail["breakdown"]}
    assert lines["no_website"]["points"] == lines["no_website"]["weight"] == 30
    assert lines["website_unreachable"]["points"] == 0
    assert detail["score"] == min(100, sum(ln["points"] for ln in detail["breakdown"]))
    assert all(ln["explanation"] for ln in detail["breakdown"])

    sushi = {s["key"]: s for s in _detail(org, prospects["Sushi Kaze"]["id"])["signals"]}
    assert (
        sushi["website_unreachable"]["state"] == "detected"
        and "service unavailable" in sushi["website_unreachable"]["evidence"]
    )
    assert sushi["booking_page_missing"]["state"] == "unknown"  # no HTML ⇒ no verdict

    cafe = {s["key"]: s for s in _detail(org, prospects["Café des Quais"]["id"])["signals"]}
    assert "facebook.com" in cafe["no_website"]["evidence"] and cafe["no_website"]["state"] == "detected"


def test_review_queue_and_audit_history(org):
    _run(org)
    prospects, _ = _by_name(org)
    marcel, forno = prospects["Chez Marcel"]["id"], prospects["Pizzeria Il Forno"]["id"]

    assert _review(org, marcel, "approve", "Looks right").json()["review_status"] == "approved"
    assert _review(org, forno, "reject").json()["review_status"] == "rejected"
    assert _by_name(org, "approved")[1]["total"] == 1
    assert _by_name(org, "pending")[1]["total"] == 5

    events = requests.get(f"{API}/prospects/{marcel}/events", headers=org).json()
    actions = [e["action"] for e in events]
    assert "prospect.approved" in actions and "prospect.created" in actions
    approved = next(e for e in events if e["action"] == "prospect.approved")
    assert approved["actor_user_id"] and approved["detail"]["to"] == "approved"
    assert "Looks right" not in str(approved["detail"])  # free text is not copied into the audit trail


def test_draft_requires_approval_and_is_idempotent_and_dry_run(org):
    _run(org)
    alice = _by_name(org)[0]["La Table d'Alice"]["id"]
    assert requests.post(f"{API}/prospects/{alice}/drafts", headers=org).status_code == 409  # still pending

    _review(org, alice, "approve")
    created = requests.post(f"{API}/prospects/{alice}/drafts", headers=org)
    assert created.status_code == 200, created.text
    draft = created.json()
    assert draft["status"] == "draft" and draft["dry_run"] is True
    assert "réserver en ligne" in draft["body"] and draft["facts"]  # backed by a detected signal
    for needle in ("figurent dans l'annuaire", "fixture_directory", "/api/unsubscribe/"):
        assert needle in draft["body"]

    again = requests.post(f"{API}/prospects/{alice}/drafts", headers=org).json()
    assert again["id"] == draft["id"]  # same derived key ⇒ no duplicate
    other = requests.post(
        f"{API}/prospects/{alice}/drafts", headers={**org, "Idempotency-Key": uuid.uuid4().hex}
    ).json()
    assert other["id"] != draft["id"]
    assert len(_detail(org, alice)["drafts"]) == 2

    assert (
        requests.post(f"{API}/prospects/drafts/{draft['id']}/review", headers=org, json={"decision": "approve"}).json()[
            "status"
        ]
        == "approved"
    )
    assert (
        requests.post(
            f"{API}/prospects/drafts/{draft['id']}/review", headers=org, json={"decision": "reject"}
        ).status_code
        == 409
    )
    usage = requests.get(f"{API}/prospects/settings", headers=org).json()["usage"]
    assert usage["drafts_generated"] == 2 and usage["discovery_run"] == 1


def test_draft_without_email_is_refused(org):
    _run(org)
    forno = _by_name(org)[0]["Pizzeria Il Forno"]["id"]  # listed with a phone but no e-mail
    _review(org, forno, "approve")
    assert requests.post(f"{API}/prospects/{forno}/drafts", headers=org).status_code == 422


def test_no_real_send_path_for_unapproved_or_dry_run_prospects(org):
    _run(org)
    alice = _by_name(org)[0]["La Table d'Alice"]["id"]
    pending = requests.post(
        f"{API}/messages/email",
        headers=org,
        json={"to": "bonjour@latable-alice.example", "subject": "s", "body": "b", "lead_id": alice},
    )
    assert pending.status_code == 403 and "review status is 'pending'" in pending.text
    blocked = [e for e in requests.get(f"{API}/prospects/{alice}/events", headers=org).json()]
    assert any(e["action"] == "send.blocked_review" for e in blocked)  # the refusal itself is on record

    _review(org, alice, "approve")
    approved = requests.post(
        f"{API}/messages/email",
        headers=org,
        json={"to": "bonjour@latable-alice.example", "subject": "s", "body": "b", "lead_id": alice},
    )
    assert approved.status_code == 403 and "dry-run" in approved.text  # approved is not enough while dry-run is on

    batch = requests.post(
        f"{API}/messages/email/batch", headers=org, json={"lead_ids": [alice], "subject": "s", "body": "b"}
    )
    assert batch.status_code == 200 and batch.json().get("sent", 0) == 0


def test_unsubscribe_link_opts_out_everywhere(org):
    _run(org)
    alice = _by_name(org)[0]["La Table d'Alice"]["id"]
    _review(org, alice, "approve")
    body = requests.post(f"{API}/prospects/{alice}/drafts", headers=org).json()["body"]
    url = re.search(r"https?://\S+/api/unsubscribe/\S+", body).group(0)
    path = "/api/unsubscribe/" + url.rsplit("/", 1)[1]

    assert requests.get(f"{BASE_URL}{path}").status_code == 200  # public, no login
    assert requests.post(f"{BASE_URL}{path}").status_code == 200  # idempotent
    assert requests.get(f"{BASE_URL}{path[:-3]}xyz").status_code == 404  # tampered token
    assert requests.get(f"{API}/unsubscribe/not-a-token").status_code == 404

    refused = requests.post(f"{API}/prospects/{alice}/drafts", headers={**org, "Idempotency-Key": uuid.uuid4().hex})
    assert refused.status_code == 409  # suppressed / opted out
    rerun = _run(org)
    assert rerun["suppressed"] >= 1 and rerun["prospects_created"] == 0
    actions = [e["action"] for e in requests.get(f"{API}/prospects/{alice}/events", headers=org).json()]
    assert "prospect.opted_out" in actions


def test_erasure_blanks_data_and_blocks_rediscovery(org):
    _run(org)
    prospects, _ = _by_name(org)
    marcel = prospects["Chez Marcel"]["id"]
    assert requests.post(f"{API}/prospects/{marcel}/erase", headers=org).status_code == 204
    assert requests.get(f"{API}/prospects/{marcel}", headers=org).status_code == 404
    assert "Chez Marcel" not in _by_name(org)[0]

    rerun = _run(org)
    assert rerun["suppressed"] >= 1
    assert "Chez Marcel" not in _by_name(org)[0]  # not rediscovered


def test_manual_suppression_blocks_matching_candidates(org):
    resp = requests.post(
        f"{API}/prospects/suppressions", headers=org, json={"domain": "https://www.sushi-kaze.example/"}
    )
    assert resp.status_code == 200 and resp.json()["added"] == 1
    assert (
        requests.post(f"{API}/prospects/suppressions", headers=org, json={"domain": "sushi-kaze.example"}).json()[
            "added"
        ]
        == 0
    )
    assert requests.post(f"{API}/prospects/suppressions", headers=org, json={}).status_code == 422
    run = _run(org)
    assert run["suppressed"] == 1 and run["prospects_created"] == 6
    assert "Sushi Kaze" not in _by_name(org)[0]


def test_score_config_versioning_and_recompute(org):
    assert requests.get(f"{API}/prospects/score-config", headers=org).json()["version"] == 0
    _run(org)
    cfg = requests.get(f"{API}/prospects/score-config", headers=org).json()
    assert cfg["version"] == 1
    before = _by_name(org)[0]["Le Petit Bouchon"]["score"]

    heavier = {**cfg, "label": "heavier", "weights": {**cfg["weights"], "no_website": 60}}
    updated = requests.put(f"{API}/prospects/score-config", headers=org, json=heavier).json()
    assert updated["version"] == 2 and updated["rescored"] >= 1
    after = _by_name(org)[0]["Le Petit Bouchon"]
    assert after["score"] == before + 30
    assert _detail(org, after["id"])["score_detail"]["version"] == 2

    same = requests.put(f"{API}/prospects/score-config", headers=org, json=heavier).json()
    assert same["version"] == 2 and same["rescored"] == 0  # unchanged config: no new version

    bad = requests.put(f"{API}/prospects/score-config", headers=org, json={**heavier, "weights": {"made_up": 1}})
    assert bad.status_code == 422
    rescored = requests.post(f"{API}/prospects/{after['id']}/rescore", headers=org)
    assert rescored.status_code == 200 and rescored.json()["version"] == 2


def test_settings_expose_flags_and_default_to_dry_run(org):
    s = requests.get(f"{API}/prospects/settings", headers=org).json()
    assert (
        s["flags"]["dry_run"] is True
        and s["flags"]["live_sending"] is False
        and s["flags"]["external_sources"] is False
    )
    assert s["sender_configured"] is True and s["usage"] == {}


def test_unknown_source_is_rejected_and_nothing_hits_the_network(org):
    resp = requests.post(f"{API}/prospects/discovery/run", headers=org, json={"source": "https://example.com/scrape"})
    assert resp.status_code == 400 and "fixture_directory" in resp.text


def test_organisations_are_isolated_and_auth_is_required():
    a, b = _register(), _register()
    _run(a)
    pid = next(iter(_by_name(a)[0].values()))["id"]
    assert _by_name(b)[1]["total"] == 0
    assert requests.get(f"{API}/prospects/{pid}", headers=b).status_code == 404
    assert requests.post(f"{API}/prospects/{pid}/review", headers=b, json={"decision": "approve"}).status_code == 404
    assert requests.get(f"{API}/prospects").status_code in (401, 403)
    assert requests.post(f"{API}/prospects/discovery/run", json={}).status_code in (401, 403)


def test_suppression_does_not_leak_between_organisations():
    a, b = _register(), _register()
    requests.post(f"{API}/prospects/suppressions", headers=a, json={"domain": "sushi-kaze.example"})
    assert _run(a)["suppressed"] == 1
    other = _run(b)
    assert other["suppressed"] == 0 and other["prospects_created"] == 7
