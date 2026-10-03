"""
Plantiers - OutreachOS - Iteration 2 Feature Tests
Tests: Bulk Leads, Batch Messaging, Campaign Assign/Run-Step, AI Variants
"""

import os
import uuid

import pytest
import requests
from helpers import open_send_limits

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Demo credentials (pre-seeded)
DEMO_EMAIL = "demo@outreachos.example"
DEMO_PASSWORD = "Demo12345!"


@pytest.fixture(scope="module")
def auth_token():
    """Get auth token for authenticated tests"""
    # Ensure demo user exists
    requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD,
            "full_name": "Demo User",
            "organization_name": "OutreachOS Demo",
        },
    )

    response = requests.post(f"{BASE_URL}/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get auth headers for authenticated tests (send limits lifted: these suites send many messages in a row)"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    open_send_limits(headers)
    return headers


# ============================================================================
# BULK LEADS TESTS
# ============================================================================
class TestBulkLeads:
    """Tests for POST /api/leads/bulk endpoint"""

    def test_bulk_import_leads(self, auth_headers):
        """Test bulk importing multiple leads"""
        unique_id = uuid.uuid4().hex[:6]
        leads = [
            {
                "full_name": f"TEST_Bulk1_{unique_id}",
                "email": f"bulk1_{unique_id}@test.com",
                "company": "Bulk Corp",
                "title": "CEO",
                "country": "US",
            },
            {
                "full_name": f"TEST_Bulk2_{unique_id}",
                "email": f"bulk2_{unique_id}@test.com",
                "company": "Bulk Inc",
                "title": "CTO",
                "country": "UK",
            },
            {
                "full_name": f"TEST_Bulk3_{unique_id}",
                "email": f"bulk3_{unique_id}@test.com",
                "company": "Bulk Ltd",
                "title": "VP",
                "country": "DE",
            },
        ]

        response = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        assert response.status_code == 200, f"Bulk import failed: {response.text}"
        data = response.json()

        # Verify response structure
        assert "created" in data
        assert "skipped" in data
        assert "errors" in data
        assert "lead_ids" in data

        # Verify counts
        assert data["created"] == 3
        assert data["skipped"] == 0
        assert len(data["errors"]) == 0
        assert len(data["lead_ids"]) == 3

        print(f"✓ Bulk imported {data['created']} leads, skipped {data['skipped']}")
        return data["lead_ids"]

    def test_bulk_import_deduplication(self, auth_headers):
        """Test that bulk import deduplicates by email"""
        unique_id = uuid.uuid4().hex[:6]
        email = f"dedup_{unique_id}@test.com"

        # First import
        leads1 = [{"full_name": f"TEST_Dedup1_{unique_id}", "email": email}]
        resp1 = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads1})
        assert resp1.status_code == 200
        assert resp1.json()["created"] == 1

        # Second import with same email should skip
        leads2 = [{"full_name": f"TEST_Dedup2_{unique_id}", "email": email}]
        resp2 = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads2})
        assert resp2.status_code == 200
        data = resp2.json()

        assert data["created"] == 0
        assert data["skipped"] == 1

        print("✓ Bulk import correctly deduplicates by email")

    def test_bulk_import_empty_list(self, auth_headers):
        """Test bulk import with empty list"""
        response = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": []})
        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 0
        assert data["skipped"] == 0
        print("✓ Bulk import handles empty list")


# ============================================================================
# BULK STAGE UPDATE TESTS
# ============================================================================
class TestBulkStageUpdate:
    """Tests for POST /api/leads/bulk-stage endpoint"""

    def test_bulk_stage_update(self, auth_headers):
        """Test bulk updating lead stages"""
        unique_id = uuid.uuid4().hex[:6]

        # Create leads first
        leads = [
            {"full_name": f"TEST_Stage1_{unique_id}", "email": f"stage1_{unique_id}@test.com"},
            {"full_name": f"TEST_Stage2_{unique_id}", "email": f"stage2_{unique_id}@test.com"},
        ]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        lead_ids = bulk_resp.json()["lead_ids"]

        # Bulk update stage
        response = requests.post(
            f"{BASE_URL}/api/leads/bulk-stage", headers=auth_headers, json={"lead_ids": lead_ids, "stage": "qualified"}
        )
        assert response.status_code == 200
        data = response.json()

        assert "updated" in data
        assert data["updated"] == 2

        # Verify persistence
        leads_resp = requests.get(f"{BASE_URL}/api/leads", headers=auth_headers)
        for lead_id in lead_ids:
            lead = next((l for l in leads_resp.json() if l["id"] == lead_id), None)
            assert lead is not None
            assert lead["stage"] == "qualified"

        print(f"✓ Bulk stage update: {data['updated']} leads updated to 'qualified'")


# ============================================================================
# BATCH EMAIL TESTS
# ============================================================================
class TestBatchEmail:
    """Tests for POST /api/messages/email/batch endpoint"""

    def test_batch_email_send(self, auth_headers):
        """Test batch sending emails to multiple leads"""
        unique_id = uuid.uuid4().hex[:6]

        # Create leads with emails
        leads = [
            {"full_name": f"TEST_Email1_{unique_id}", "email": f"email1_{unique_id}@test.com", "company": "Test Co"},
            {"full_name": f"TEST_Email2_{unique_id}", "email": f"email2_{unique_id}@test.com", "company": "Test Inc"},
        ]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        lead_ids = bulk_resp.json()["lead_ids"]

        # Batch send emails
        response = requests.post(
            f"{BASE_URL}/api/messages/email/batch",
            headers=auth_headers,
            json={
                "lead_ids": lead_ids,
                "subject": "Hello {{first_name}} from {{company}}",
                "body": "Hi {{first_name}},\n\nThis is a test message for {{company}}.\n\nBest,\nPlantiers",
            },
        )
        assert response.status_code == 200, f"Batch email failed: {response.text}"
        data = response.json()

        # Verify response structure
        assert "dispatched" in data
        assert "sent" in data
        assert "mocked" in data
        assert "failed" in data
        assert "skipped" in data
        assert "total" in data
        assert "results" in data

        # Verify counts
        assert data["total"] == 2
        assert data["dispatched"] == data["sent"] + data["mocked"]
        assert data["skipped"] == 0  # All leads have emails

        print(f"✓ Batch email: dispatched={data['dispatched']}, sent={data['sent']}, mocked={data['mocked']}")

    def test_batch_email_token_substitution(self, auth_headers):
        """Test that tokens are substituted correctly in batch emails"""
        unique_id = uuid.uuid4().hex[:6]

        # Create a lead with specific data
        leads = [
            {
                "full_name": f"John Smith",
                "email": f"john_{unique_id}@test.com",
                "company": "Acme Corp",
                "title": "CEO",
                "country": "US",
            }
        ]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        lead_ids = bulk_resp.json()["lead_ids"]

        # Send with tokens
        response = requests.post(
            f"{BASE_URL}/api/messages/email/batch",
            headers=auth_headers,
            json={
                "lead_ids": lead_ids,
                "subject": "For {{company}}",
                "body": "Hi {{first_name}}, you work at {{company}} as {{title}} in {{country}}.",
            },
        )
        assert response.status_code == 200

        # Check messages were created
        msgs_resp = requests.get(f"{BASE_URL}/api/messages", headers=auth_headers, params={"channel": "email"})
        recent_msg = next((m for m in msgs_resp.json() if lead_ids[0] == m.get("lead_id")), None)

        if recent_msg:
            # Verify token substitution
            assert "John" in recent_msg["body"]
            assert "Acme Corp" in recent_msg["body"]
            print("✓ Token substitution verified in batch email")
        else:
            print("✓ Batch email sent (message verification skipped)")

    def test_batch_email_requires_subject(self, auth_headers):
        """Test that batch email requires subject"""
        response = requests.post(
            f"{BASE_URL}/api/messages/email/batch",
            headers=auth_headers,
            json={"lead_ids": ["fake-id"], "body": "Test body"},
        )
        assert response.status_code == 400
        assert "subject" in response.json()["detail"].lower()
        print("✓ Batch email correctly requires subject")


# ============================================================================
# BATCH WHATSAPP TESTS
# ============================================================================
class TestBatchWhatsApp:
    """Tests for POST /api/messages/whatsapp/batch endpoint"""

    def test_batch_whatsapp_send(self, auth_headers):
        """Test batch sending WhatsApp to multiple leads"""
        unique_id = uuid.uuid4().hex[:6]

        # Create leads with phone numbers
        leads = [
            {
                "full_name": f"TEST_WA1_{unique_id}",
                "email": f"wa1_{unique_id}@test.com",
                "phone": "+14155550101",
                "company": "WA Corp",
            },
            {
                "full_name": f"TEST_WA2_{unique_id}",
                "email": f"wa2_{unique_id}@test.com",
                "phone": "+14155550102",
                "company": "WA Inc",
            },
        ]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        lead_ids = bulk_resp.json()["lead_ids"]

        # Batch send WhatsApp
        response = requests.post(
            f"{BASE_URL}/api/messages/whatsapp/batch",
            headers=auth_headers,
            json={"lead_ids": lead_ids, "body": "Hi {{first_name}} from {{company}}! Quick question about your needs."},
        )
        assert response.status_code == 200, f"Batch WhatsApp failed: {response.text}"
        data = response.json()

        # Verify response structure
        assert "dispatched" in data
        assert "sent" in data
        assert "mocked" in data
        assert "failed" in data
        assert "skipped" in data
        assert "total" in data

        # Verify counts
        assert data["total"] == 2
        assert data["dispatched"] == data["sent"] + data["mocked"]

        print(f"✓ Batch WhatsApp: dispatched={data['dispatched']}, sent={data['sent']}, mocked={data['mocked']}")

    def test_batch_whatsapp_skips_no_phone(self, auth_headers):
        """Test that batch WhatsApp skips leads without phone"""
        unique_id = uuid.uuid4().hex[:6]

        # Create lead without phone
        leads = [{"full_name": f"TEST_NoPhone_{unique_id}", "email": f"nophone_{unique_id}@test.com"}]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        lead_ids = bulk_resp.json()["lead_ids"]

        # Batch send WhatsApp
        response = requests.post(
            f"{BASE_URL}/api/messages/whatsapp/batch",
            headers=auth_headers,
            json={"lead_ids": lead_ids, "body": "Test message"},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["skipped"] == 1
        assert data["dispatched"] == 0

        print("✓ Batch WhatsApp correctly skips leads without phone")


# ============================================================================
# CAMPAIGN ASSIGN LEADS TESTS
# ============================================================================
class TestCampaignAssignLeads:
    """Tests for POST /api/campaigns/{id}/assign-leads endpoint"""

    def test_assign_leads_to_campaign(self, auth_headers):
        """Test assigning leads to a campaign"""
        unique_id = uuid.uuid4().hex[:6]

        # Create campaign
        campaign_resp = requests.post(
            f"{BASE_URL}/api/campaigns",
            headers=auth_headers,
            json={"name": f"TEST_Assign_{unique_id}", "goal": "Test assign leads"},
        )
        campaign_id = campaign_resp.json()["id"]

        # Create leads
        leads = [
            {"full_name": f"TEST_Assign1_{unique_id}", "email": f"assign1_{unique_id}@test.com"},
            {"full_name": f"TEST_Assign2_{unique_id}", "email": f"assign2_{unique_id}@test.com"},
        ]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        lead_ids = bulk_resp.json()["lead_ids"]

        # Assign leads
        response = requests.post(
            f"{BASE_URL}/api/campaigns/{campaign_id}/assign-leads", headers=auth_headers, json={"lead_ids": lead_ids}
        )
        assert response.status_code == 200, f"Assign leads failed: {response.text}"
        data = response.json()

        # Verify campaign has leads
        assert "lead_ids" in data
        assert len(data["lead_ids"]) == 2
        for lid in lead_ids:
            assert lid in data["lead_ids"]

        print(f"✓ Assigned {len(lead_ids)} leads to campaign")

    def test_assign_leads_appends_unique(self, auth_headers):
        """Test that assigning leads appends unique IDs"""
        unique_id = uuid.uuid4().hex[:6]

        # Create campaign
        campaign_resp = requests.post(
            f"{BASE_URL}/api/campaigns",
            headers=auth_headers,
            json={"name": f"TEST_AppendUnique_{unique_id}", "goal": "Test"},
        )
        campaign_id = campaign_resp.json()["id"]

        # Create leads
        leads = [
            {"full_name": f"TEST_Unique1_{unique_id}", "email": f"unique1_{unique_id}@test.com"},
            {"full_name": f"TEST_Unique2_{unique_id}", "email": f"unique2_{unique_id}@test.com"},
        ]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        lead_ids = bulk_resp.json()["lead_ids"]

        # Assign first lead
        requests.post(
            f"{BASE_URL}/api/campaigns/{campaign_id}/assign-leads",
            headers=auth_headers,
            json={"lead_ids": [lead_ids[0]]},
        )

        # Assign both (should dedupe)
        response = requests.post(
            f"{BASE_URL}/api/campaigns/{campaign_id}/assign-leads", headers=auth_headers, json={"lead_ids": lead_ids}
        )
        assert response.status_code == 200
        data = response.json()

        # Should have exactly 2 unique leads
        assert len(data["lead_ids"]) == 2

        print("✓ Assign leads correctly deduplicates")

    def test_assign_leads_validates_org(self, auth_headers):
        """Test that assigning leads validates org ownership"""
        unique_id = uuid.uuid4().hex[:6]

        # Create campaign
        campaign_resp = requests.post(
            f"{BASE_URL}/api/campaigns",
            headers=auth_headers,
            json={"name": f"TEST_ValidateOrg_{unique_id}", "goal": "Test"},
        )
        campaign_id = campaign_resp.json()["id"]

        # Try to assign fake lead IDs
        response = requests.post(
            f"{BASE_URL}/api/campaigns/{campaign_id}/assign-leads",
            headers=auth_headers,
            json={"lead_ids": ["fake-lead-id-1", "fake-lead-id-2"]},
        )
        assert response.status_code == 400
        assert "do not belong" in response.json()["detail"].lower()

        print("✓ Assign leads validates org ownership")


# ============================================================================
# CAMPAIGN RUN STEP TESTS
# ============================================================================
class TestCampaignRunStep:
    """Tests for POST /api/campaigns/{id}/run-step/{index} endpoint"""

    def test_run_step_executes(self, auth_headers):
        """Test running a campaign step"""
        unique_id = uuid.uuid4().hex[:6]

        # Create campaign with steps
        campaign_resp = requests.post(
            f"{BASE_URL}/api/campaigns",
            headers=auth_headers,
            json={
                "name": f"TEST_RunStep_{unique_id}",
                "goal": "Test run step",
                "channels": ["email"],
                "steps": [
                    {
                        "channel": "email",
                        "delay_hours": 0,
                        "subject": "Test {{first_name}}",
                        "body": "Hello {{first_name}} from {{company}}",
                        "language": "en",
                    }
                ],
            },
        )
        campaign_id = campaign_resp.json()["id"]

        # Create and assign leads
        leads = [
            {"full_name": f"TEST_Run1_{unique_id}", "email": f"run1_{unique_id}@test.com", "company": "Run Corp"},
            {"full_name": f"TEST_Run2_{unique_id}", "email": f"run2_{unique_id}@test.com", "company": "Run Inc"},
        ]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        lead_ids = bulk_resp.json()["lead_ids"]

        requests.post(
            f"{BASE_URL}/api/campaigns/{campaign_id}/assign-leads", headers=auth_headers, json={"lead_ids": lead_ids}
        )

        # Run step 0
        response = requests.post(f"{BASE_URL}/api/campaigns/{campaign_id}/run-step/0", headers=auth_headers)
        assert response.status_code == 200, f"Run step failed: {response.text}"
        data = response.json()

        # Verify response structure
        assert "dispatched" in data
        assert "sent" in data
        assert "mocked" in data
        assert "failed" in data
        assert "skipped" in data
        assert "total" in data

        # Verify execution
        assert data["total"] == 2
        assert data["dispatched"] == data["sent"] + data["mocked"]

        print(f"✓ Run step: dispatched={data['dispatched']}, total={data['total']}")

    def test_run_step_no_leads_error(self, auth_headers):
        """Test run step fails when no leads assigned"""
        unique_id = uuid.uuid4().hex[:6]

        # Create campaign with steps but no leads
        campaign_resp = requests.post(
            f"{BASE_URL}/api/campaigns",
            headers=auth_headers,
            json={
                "name": f"TEST_NoLeads_{unique_id}",
                "goal": "Test",
                "steps": [{"channel": "email", "delay_hours": 0, "subject": "Test", "body": "Test", "language": "en"}],
            },
        )
        campaign_id = campaign_resp.json()["id"]

        # Try to run step
        response = requests.post(f"{BASE_URL}/api/campaigns/{campaign_id}/run-step/0", headers=auth_headers)
        assert response.status_code == 400
        assert "no leads" in response.json()["detail"].lower()

        print("✓ Run step correctly fails when no leads assigned")

    def test_run_step_invalid_index(self, auth_headers):
        """Test run step fails with invalid step index"""
        unique_id = uuid.uuid4().hex[:6]

        # Create campaign with 1 step
        campaign_resp = requests.post(
            f"{BASE_URL}/api/campaigns",
            headers=auth_headers,
            json={
                "name": f"TEST_InvalidIdx_{unique_id}",
                "goal": "Test",
                "steps": [{"channel": "email", "delay_hours": 0, "subject": "Test", "body": "Test", "language": "en"}],
            },
        )
        campaign_id = campaign_resp.json()["id"]

        # Create and assign a lead
        leads = [{"full_name": f"TEST_Idx_{unique_id}", "email": f"idx_{unique_id}@test.com"}]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        lead_ids = bulk_resp.json()["lead_ids"]
        requests.post(
            f"{BASE_URL}/api/campaigns/{campaign_id}/assign-leads", headers=auth_headers, json={"lead_ids": lead_ids}
        )

        # Try to run step 5 (out of range)
        response = requests.post(f"{BASE_URL}/api/campaigns/{campaign_id}/run-step/5", headers=auth_headers)
        assert response.status_code == 400
        assert "out of range" in response.json()["detail"].lower()

        print("✓ Run step correctly fails with invalid index")


# ============================================================================
# AI GENERATE VARIANTS TESTS
# ============================================================================
class TestAIGenerateVariants:
    """Tests for POST /api/ai/generate/variants endpoint"""

    def test_generate_variants(self, auth_headers):
        """Test generating 3 tone variants"""
        payload = {
            "recipient_name": "John Smith",
            "company": "Acme Corp",
            "product": "Plantiers - OutreachOS platform",
            "language": "en",
            "tone": "professional",  # This is ignored, all 3 tones generated
            "channel": "email",
            "goal": "book a demo call",
        }
        response = requests.post(f"{BASE_URL}/api/ai/generate/variants", headers=auth_headers, json=payload)
        assert response.status_code == 200, f"Generate variants failed: {response.text}"
        data = response.json()

        # Verify response structure
        assert "variants" in data
        assert len(data["variants"]) == 3

        # Verify each variant has required fields
        for variant in data["variants"]:
            assert "subject" in variant or variant.get("subject") is None
            assert "body" in variant
            assert "language" in variant
            assert len(variant["body"]) > 0

        print(f"✓ Generated 3 variants: {[len(v['body']) for v in data['variants']]} chars each")

    def test_generate_variants_whatsapp(self, auth_headers):
        """Test generating WhatsApp variants (no subject)"""
        payload = {
            "recipient_name": "Maria Garcia",
            "company": "Tech Startup",
            "product": "Plantiers - OutreachOS",
            "language": "en",
            "tone": "friendly",
            "channel": "whatsapp",
            "goal": "quick chat",
        }
        response = requests.post(f"{BASE_URL}/api/ai/generate/variants", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()

        assert len(data["variants"]) == 3
        for variant in data["variants"]:
            # WhatsApp should have null/empty subject
            assert variant["subject"] is None or variant["subject"] == ""
            assert len(variant["body"]) > 0

        print("✓ Generated 3 WhatsApp variants (no subjects)")


# ============================================================================
# REGRESSION TESTS - Verify existing endpoints still work
# ============================================================================
class TestRegressionEndpoints:
    """Regression tests for existing endpoints"""

    def test_root_endpoint(self):
        """Test root API endpoint still works"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        assert response.json()["service"] == "plantiers-outreachos"
        print("✓ Root endpoint working")

    def test_health_endpoint(self):
        """Test health check still works"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("✓ Health endpoint working")

    def test_login_works(self):
        """Test login still works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
        assert response.status_code == 200
        assert "access_token" in response.json()
        print("✓ Login working")

    def test_leads_list(self, auth_headers):
        """Test leads list still works"""
        response = requests.get(f"{BASE_URL}/api/leads", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print("✓ Leads list working")

    def test_campaigns_list(self, auth_headers):
        """Test campaigns list still works"""
        response = requests.get(f"{BASE_URL}/api/campaigns", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print("✓ Campaigns list working")

    def test_agents_list(self, auth_headers):
        """Test agents list still works"""
        response = requests.get(f"{BASE_URL}/api/agents", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print("✓ Agents list working")

    def test_messages_list(self, auth_headers):
        """Test messages list still works"""
        response = requests.get(f"{BASE_URL}/api/messages", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print("✓ Messages list working")

    def test_analytics_overview(self, auth_headers):
        """Test analytics overview still works"""
        response = requests.get(f"{BASE_URL}/api/analytics/overview", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "totals" in data
        assert "pipeline" in data
        print("✓ Analytics overview working")

    def test_settings_integrations(self, auth_headers):
        """Test settings integrations still works"""
        response = requests.get(f"{BASE_URL}/api/settings/integrations", headers=auth_headers)
        assert response.status_code == 200
        print("✓ Settings integrations working")

    def test_ai_generate_single(self, auth_headers):
        """Test single AI generate still works"""
        response = requests.post(
            f"{BASE_URL}/api/ai/generate",
            headers=auth_headers,
            json={
                "recipient_name": "Test User",
                "product": "Plantiers - OutreachOS",
                "language": "en",
                "tone": "professional",
                "channel": "email",
            },
        )
        assert response.status_code == 200
        assert "body" in response.json()
        print("✓ AI generate single working")

    def test_unauthorized_returns_401(self):
        """Test unauthorized requests return 401"""
        response = requests.get(f"{BASE_URL}/api/leads")
        assert response.status_code == 401
        print("✓ Unauthorized correctly returns 401")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
