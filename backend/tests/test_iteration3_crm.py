"""
ClawPilot SaaS Platform - Iteration 3 Feature Tests
Tests: CRM Notes, Tasks, Tags (catalog + attach/detach), real analytics splits
"""

import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

DEMO_EMAIL = "demo@clawpilot.io"
DEMO_PASSWORD = "Demo12345!"


@pytest.fixture(scope="module")
def auth_token():
    requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD,
            "full_name": "Demo User",
            "organization_name": "ClawPilot Demo",
        },
    )
    response = requests.post(f"{BASE_URL}/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


def _create_lead(auth_headers, unique_id):
    resp = requests.post(
        f"{BASE_URL}/api/leads",
        headers=auth_headers,
        json={"full_name": f"TEST_CRM_{unique_id}", "email": f"crm_{unique_id}@test.com", "country": "FR"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


# ============================================================================
# NOTES
# ============================================================================
class TestNotes:
    def test_create_and_list_note(self, auth_headers):
        unique_id = uuid.uuid4().hex[:6]
        lead_id = _create_lead(auth_headers, unique_id)

        resp = requests.post(
            f"{BASE_URL}/api/notes", headers=auth_headers, json={"lead_id": lead_id, "body": "Left a voicemail."}
        )
        assert resp.status_code == 200, resp.text
        note = resp.json()
        assert note["lead_id"] == lead_id
        assert note["body"] == "Left a voicemail."
        assert note["author_user_id"]

        resp = requests.get(f"{BASE_URL}/api/notes", headers=auth_headers, params={"lead_id": lead_id})
        assert resp.status_code == 200
        notes = resp.json()
        assert len(notes) == 1
        assert notes[0]["id"] == note["id"]

    def test_note_requires_a_target(self, auth_headers):
        resp = requests.post(f"{BASE_URL}/api/notes", headers=auth_headers, json={"body": "orphan note"})
        assert resp.status_code == 422, resp.text

    def test_delete_note(self, auth_headers):
        unique_id = uuid.uuid4().hex[:6]
        lead_id = _create_lead(auth_headers, unique_id)
        resp = requests.post(f"{BASE_URL}/api/notes", headers=auth_headers, json={"lead_id": lead_id, "body": "x"})
        note_id = resp.json()["id"]

        resp = requests.delete(f"{BASE_URL}/api/notes/{note_id}", headers=auth_headers)
        assert resp.status_code == 200

        resp = requests.get(f"{BASE_URL}/api/notes", headers=auth_headers, params={"lead_id": lead_id})
        assert resp.json() == []

    def test_delete_note_not_found(self, auth_headers):
        resp = requests.delete(f"{BASE_URL}/api/notes/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404


# ============================================================================
# TASKS
# ============================================================================
class TestCrmTasks:
    def test_create_update_task(self, auth_headers):
        unique_id = uuid.uuid4().hex[:6]
        lead_id = _create_lead(auth_headers, unique_id)

        resp = requests.post(
            f"{BASE_URL}/api/tasks", headers=auth_headers, json={"lead_id": lead_id, "title": "Follow up Friday"}
        )
        assert resp.status_code == 200, resp.text
        task = resp.json()
        assert task["status"] == "open"
        assert task["title"] == "Follow up Friday"

        resp = requests.patch(f"{BASE_URL}/api/tasks/{task['id']}", headers=auth_headers, json={"status": "done"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "done"

    def test_list_tasks_filtered_by_status(self, auth_headers):
        unique_id = uuid.uuid4().hex[:6]
        lead_id = _create_lead(auth_headers, unique_id)
        requests.post(f"{BASE_URL}/api/tasks", headers=auth_headers, json={"lead_id": lead_id, "title": "Task A"})
        resp = requests.post(
            f"{BASE_URL}/api/tasks", headers=auth_headers, json={"lead_id": lead_id, "title": "Task B"}
        )
        task_b = resp.json()["id"]
        requests.patch(f"{BASE_URL}/api/tasks/{task_b}", headers=auth_headers, json={"status": "done"})

        resp = requests.get(
            f"{BASE_URL}/api/tasks", headers=auth_headers, params={"lead_id": lead_id, "status": "open"}
        )
        assert resp.status_code == 200
        titles = [t["title"] for t in resp.json()]
        assert titles == ["Task A"]

    def test_delete_task(self, auth_headers):
        unique_id = uuid.uuid4().hex[:6]
        lead_id = _create_lead(auth_headers, unique_id)
        resp = requests.post(f"{BASE_URL}/api/tasks", headers=auth_headers, json={"lead_id": lead_id, "title": "x"})
        task_id = resp.json()["id"]

        resp = requests.delete(f"{BASE_URL}/api/tasks/{task_id}", headers=auth_headers)
        assert resp.status_code == 200

        resp = requests.get(f"{BASE_URL}/api/tasks", headers=auth_headers, params={"lead_id": lead_id})
        assert resp.json() == []


# ============================================================================
# TAGS
# ============================================================================
class TestTags:
    def test_create_list_tag(self, auth_headers):
        unique_id = uuid.uuid4().hex[:6]
        resp = requests.post(
            f"{BASE_URL}/api/tags", headers=auth_headers, json={"name": f"VIP_{unique_id}", "color": "#DC2626"}
        )
        assert resp.status_code == 200, resp.text
        tag = resp.json()
        assert tag["name"] == f"VIP_{unique_id}"
        assert tag["color"] == "#DC2626"

        resp = requests.get(f"{BASE_URL}/api/tags", headers=auth_headers)
        assert resp.status_code == 200
        assert any(t["id"] == tag["id"] for t in resp.json())

    def test_duplicate_tag_name_rejected(self, auth_headers):
        unique_id = uuid.uuid4().hex[:6]
        name = f"Duplicate_{unique_id}"
        resp = requests.post(f"{BASE_URL}/api/tags", headers=auth_headers, json={"name": name})
        assert resp.status_code == 200
        resp = requests.post(f"{BASE_URL}/api/tags", headers=auth_headers, json={"name": name})
        assert resp.status_code == 400

    def test_attach_detach_tag_updates_lead(self, auth_headers):
        unique_id = uuid.uuid4().hex[:6]
        lead_id = _create_lead(auth_headers, unique_id)
        resp = requests.post(f"{BASE_URL}/api/tags", headers=auth_headers, json={"name": f"Hot_{unique_id}"})
        tag_id = resp.json()["id"]

        resp = requests.post(f"{BASE_URL}/api/leads/{lead_id}/tags/{tag_id}", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert f"Hot_{unique_id}" in resp.json()["tags"]

        resp = requests.get(f"{BASE_URL}/api/leads", headers=auth_headers)
        lead = next(x for x in resp.json() if x["id"] == lead_id)
        assert f"Hot_{unique_id}" in lead["tags"]

        resp = requests.delete(f"{BASE_URL}/api/leads/{lead_id}/tags/{tag_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert f"Hot_{unique_id}" not in resp.json()["tags"]

    def test_delete_tag_cleans_up_lead_cache(self, auth_headers):
        unique_id = uuid.uuid4().hex[:6]
        lead_id = _create_lead(auth_headers, unique_id)
        resp = requests.post(f"{BASE_URL}/api/tags", headers=auth_headers, json={"name": f"Stale_{unique_id}"})
        tag_id = resp.json()["id"]
        requests.post(f"{BASE_URL}/api/leads/{lead_id}/tags/{tag_id}", headers=auth_headers)

        resp = requests.delete(f"{BASE_URL}/api/tags/{tag_id}", headers=auth_headers)
        assert resp.status_code == 200

        resp = requests.get(f"{BASE_URL}/api/leads", headers=auth_headers)
        lead = next(x for x in resp.json() if x["id"] == lead_id)
        assert f"Stale_{unique_id}" not in lead["tags"]

    def test_attach_unknown_tag_404(self, auth_headers):
        unique_id = uuid.uuid4().hex[:6]
        lead_id = _create_lead(auth_headers, unique_id)
        resp = requests.post(f"{BASE_URL}/api/leads/{lead_id}/tags/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404


# ============================================================================
# ANALYTICS — real channel split / top countries (regression guard against the
# old hardcoded 68/32 split and fixed 6-country guess list)
# ============================================================================
class TestAnalyticsRealSplits:
    def test_channel_split_shape(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/analytics/overview", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        channels = {c["channel"] for c in data["channel_split"]}
        assert channels == {"Email", "WhatsApp"}
        total_pct = sum(c["value"] for c in data["channel_split"])
        assert total_pct in (0, 100), f"channel split percentages should sum to 0 or 100, got {total_pct}"

    def test_top_countries_reflects_real_leads(self, auth_headers):
        unique_id = uuid.uuid4().hex[:6]
        _create_lead(auth_headers, unique_id)  # country=FR

        resp = requests.get(f"{BASE_URL}/api/analytics/overview", headers=auth_headers)
        assert resp.status_code == 200
        countries = [c["country"] for c in resp.json()["top_countries"]]
        assert "FR" in countries
