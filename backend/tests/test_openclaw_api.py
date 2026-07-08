"""
ClawPilot SaaS Platform - Backend API Tests
Tests: Auth, Leads, Campaigns, Agents, Messages, AI, Analytics, Settings
"""

import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
TEST_EMAIL = f"test_{uuid.uuid4().hex[:8]}@clawpilot.io"
TEST_PASSWORD = "TestPass123!"
TEST_ORG = "Test Organization"
TEST_NAME = "Test User"

# Demo credentials (pre-seeded)
DEMO_EMAIL = "demo@clawpilot.io"
DEMO_PASSWORD = "Demo12345!"


class TestHealthAndRoot:
    """Basic health check tests"""

    def test_root_endpoint(self):
        """Test root API endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "clawpilot"
        assert data["status"] == "ok"
        print("✓ Root endpoint working")

    def test_health_endpoint(self):
        """Test health check endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print("✓ Health endpoint working")


class TestAuthentication:
    """Authentication flow tests"""

    def test_register_new_user(self):
        """Test user registration creates org+user and returns JWT"""
        response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD,
                "full_name": TEST_NAME,
                "organization_name": TEST_ORG,
            },
        )
        assert response.status_code == 200, f"Register failed: {response.text}"
        data = response.json()

        # Verify response structure
        assert "access_token" in data
        assert "user" in data
        assert "organization" in data
        assert data["token_type"] == "bearer"

        # Verify user data
        assert data["user"]["email"] == TEST_EMAIL.lower()
        assert data["user"]["full_name"] == TEST_NAME
        assert data["user"]["role"] == "owner"

        # Verify org data
        assert data["organization"]["name"] == TEST_ORG
        assert data["organization"]["plan"] == "pro"

        print(f"✓ Registration successful for {TEST_EMAIL}")

    def test_register_duplicate_email(self):
        """Test registration fails for duplicate email"""
        response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD,
                "full_name": TEST_NAME,
                "organization_name": TEST_ORG,
            },
        )
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()
        print("✓ Duplicate email rejected correctly")

    def test_login_with_demo_credentials(self):
        """Test login with demo credentials"""
        # First try to register demo user (may already exist)
        requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": DEMO_EMAIL,
                "password": DEMO_PASSWORD,
                "full_name": "Demo User",
                "organization_name": "ClawPilot Demo",
            },
        )

        # Now login
        response = requests.post(f"{BASE_URL}/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()

        assert "access_token" in data
        assert data["user"]["email"] == DEMO_EMAIL
        print("✓ Demo login successful")
        return data["access_token"]

    def test_login_invalid_credentials(self):
        """Test login fails with invalid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login", json={"email": "wrong@email.com", "password": "wrongpassword"}
        )
        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()
        print("✓ Invalid credentials rejected correctly")

    def test_me_endpoint_authorized(self):
        """Test /auth/me returns current user when authorized"""
        # Login first
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
        token = login_resp.json()["access_token"]

        # Call /me
        response = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert "user" in data
        assert "organization" in data
        assert data["user"]["email"] == DEMO_EMAIL
        print("✓ /auth/me returns user data correctly")

    def test_me_endpoint_unauthorized(self):
        """Test /auth/me returns 401 without token"""
        response = requests.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401
        print("✓ /auth/me rejects unauthorized requests")

    def test_me_endpoint_invalid_token(self):
        """Test /auth/me returns 401 with invalid token"""
        response = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": "Bearer invalid_token_here"})
        assert response.status_code == 401
        print("✓ /auth/me rejects invalid tokens")


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
            "organization_name": "ClawPilot Demo",
        },
    )

    response = requests.post(f"{BASE_URL}/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get auth headers for authenticated tests"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestAnalytics:
    """Analytics endpoint tests"""

    def test_analytics_overview(self, auth_headers):
        """Test analytics overview returns all required data"""
        response = requests.get(f"{BASE_URL}/api/analytics/overview", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        # Verify all required fields
        assert "totals" in data
        assert "leads_total" in data
        assert "agents_running" in data
        assert "agents_total" in data
        assert "pipeline" in data
        assert "timeseries" in data
        assert "channel_split" in data
        assert "top_countries" in data

        # Verify totals structure
        totals = data["totals"]
        assert "sent" in totals
        assert "opened" in totals
        assert "replied" in totals
        assert "converted" in totals

        # Verify timeseries has 14 days
        assert len(data["timeseries"]) == 14

        # Verify pipeline stages
        pipeline = data["pipeline"]
        for stage in ["new", "contacted", "engaged", "qualified", "won", "lost"]:
            assert stage in pipeline

        print("✓ Analytics overview returns complete data")

    def test_analytics_activity(self, auth_headers):
        """Test analytics activity returns recent items"""
        response = requests.get(f"{BASE_URL}/api/analytics/activity", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        if len(data) > 0:
            item = data[0]
            assert "id" in item
            assert "kind" in item
            assert "title" in item
            assert "created_at" in item

        print(f"✓ Analytics activity returns {len(data)} items")

    def test_analytics_unauthorized(self):
        """Test analytics endpoints require auth"""
        response = requests.get(f"{BASE_URL}/api/analytics/overview")
        assert response.status_code == 401
        print("✓ Analytics endpoints require authentication")


class TestLeads:
    """Leads CRUD tests"""

    def test_list_leads(self, auth_headers):
        """Test listing leads"""
        response = requests.get(f"{BASE_URL}/api/leads", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Listed {len(data)} leads")

    def test_create_lead(self, auth_headers):
        """Test creating a new lead"""
        lead_data = {
            "full_name": "TEST_John Doe",
            "email": "test_john@example.com",
            "company": "Test Corp",
            "title": "CEO",
            "country": "US",
            "language": "en",
        }
        response = requests.post(f"{BASE_URL}/api/leads", headers=auth_headers, json=lead_data)
        assert response.status_code == 200
        data = response.json()

        assert data["full_name"] == lead_data["full_name"]
        assert data["email"] == lead_data["email"]
        assert data["company"] == lead_data["company"]
        assert data["stage"] == "new"
        assert "id" in data

        print(f"✓ Created lead: {data['id']}")
        return data["id"]

    def test_update_lead_stage(self, auth_headers):
        """Test updating lead stage"""
        # Create a lead first
        create_resp = requests.post(
            f"{BASE_URL}/api/leads",
            headers=auth_headers,
            json={"full_name": "TEST_Stage Update", "email": "test_stage@example.com"},
        )
        lead_id = create_resp.json()["id"]

        # Update stage
        response = requests.patch(f"{BASE_URL}/api/leads/{lead_id}", headers=auth_headers, json={"stage": "contacted"})
        assert response.status_code == 200
        assert response.json()["stage"] == "contacted"

        # Verify persistence
        get_resp = requests.get(f"{BASE_URL}/api/leads", headers=auth_headers)
        leads = [l for l in get_resp.json() if l["id"] == lead_id]
        assert len(leads) == 1
        assert leads[0]["stage"] == "contacted"

        print("✓ Lead stage updated and persisted")

    def test_delete_lead(self, auth_headers):
        """Test deleting a lead"""
        # Create a lead first
        create_resp = requests.post(
            f"{BASE_URL}/api/leads",
            headers=auth_headers,
            json={"full_name": "TEST_To Delete", "email": "test_delete@example.com"},
        )
        lead_id = create_resp.json()["id"]

        # Delete
        response = requests.delete(f"{BASE_URL}/api/leads/{lead_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["ok"] == True

        # Verify deletion
        get_resp = requests.get(f"{BASE_URL}/api/leads", headers=auth_headers)
        leads = [l for l in get_resp.json() if l["id"] == lead_id]
        assert len(leads) == 0

        print("✓ Lead deleted successfully")

    def test_enrich_leads(self, auth_headers):
        """Test lead enrichment"""
        response = requests.post(f"{BASE_URL}/api/leads/enrich", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "enriched" in data
        print(f"✓ Enriched {data['enriched']} leads")

    def test_search_leads(self, auth_headers):
        """Test lead search"""
        response = requests.get(f"{BASE_URL}/api/leads", headers=auth_headers, params={"search": "Priya"})
        assert response.status_code == 200
        print("✓ Lead search works")


class TestCampaigns:
    """Campaign CRUD tests"""

    def test_list_campaigns(self, auth_headers):
        """Test listing campaigns"""
        response = requests.get(f"{BASE_URL}/api/campaigns", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Listed {len(data)} campaigns")

    def test_create_campaign(self, auth_headers):
        """Test creating a campaign"""
        campaign_data = {
            "name": "TEST_Campaign",
            "goal": "Test goal",
            "channels": ["email"],
            "steps": [{"channel": "email", "delay_hours": 0, "subject": "Test", "body": "Test body", "language": "en"}],
        }
        response = requests.post(f"{BASE_URL}/api/campaigns", headers=auth_headers, json=campaign_data)
        assert response.status_code == 200
        data = response.json()

        assert data["name"] == campaign_data["name"]
        assert data["goal"] == campaign_data["goal"]
        assert data["status"] == "draft"
        assert "id" in data

        print(f"✓ Created campaign: {data['id']}")
        return data["id"]

    def test_update_campaign_status(self, auth_headers):
        """Test updating campaign status"""
        # Create campaign
        create_resp = requests.post(
            f"{BASE_URL}/api/campaigns", headers=auth_headers, json={"name": "TEST_Status Update", "goal": "Test"}
        )
        campaign_id = create_resp.json()["id"]

        # Update status
        response = requests.patch(
            f"{BASE_URL}/api/campaigns/{campaign_id}", headers=auth_headers, json={"status": "running"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "running"
        print("✓ Campaign status updated")

    def test_launch_campaign(self, auth_headers):
        """Test launching a campaign"""
        # Create campaign
        create_resp = requests.post(
            f"{BASE_URL}/api/campaigns", headers=auth_headers, json={"name": "TEST_Launch", "goal": "Test launch"}
        )
        campaign_id = create_resp.json()["id"]

        # Launch
        response = requests.post(f"{BASE_URL}/api/campaigns/{campaign_id}/launch", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] == True
        assert "dispatched" in data
        print(f"✓ Campaign launched, dispatched {data['dispatched']} messages")

    def test_delete_campaign(self, auth_headers):
        """Test deleting a campaign"""
        # Create campaign
        create_resp = requests.post(
            f"{BASE_URL}/api/campaigns", headers=auth_headers, json={"name": "TEST_Delete", "goal": "Test delete"}
        )
        campaign_id = create_resp.json()["id"]

        # Delete
        response = requests.delete(f"{BASE_URL}/api/campaigns/{campaign_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["ok"] == True
        print("✓ Campaign deleted")


class TestAgents:
    """Agent orchestration tests"""

    def test_list_agents(self, auth_headers):
        """Test listing agents"""
        response = requests.get(f"{BASE_URL}/api/agents", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Listed {len(data)} agents")

    def test_create_agent(self, auth_headers):
        """Test spawning a new agent"""
        agent_data = {"name": "TEST_Agent", "role": "outreach"}
        response = requests.post(f"{BASE_URL}/api/agents", headers=auth_headers, json=agent_data)
        assert response.status_code == 200
        data = response.json()

        assert data["name"] == agent_data["name"]
        assert data["role"] == agent_data["role"]
        assert data["status"] == "idle"
        assert "id" in data

        print(f"✓ Spawned agent: {data['id']}")
        return data["id"]

    def test_toggle_agent(self, auth_headers):
        """Test toggling agent status"""
        # Create agent
        create_resp = requests.post(
            f"{BASE_URL}/api/agents", headers=auth_headers, json={"name": "TEST_Toggle", "role": "enrichment"}
        )
        agent_id = create_resp.json()["id"]

        # Toggle to running
        response = requests.post(f"{BASE_URL}/api/agents/{agent_id}/toggle", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "running"

        # Toggle back to paused
        response = requests.post(f"{BASE_URL}/api/agents/{agent_id}/toggle", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "paused"

        print("✓ Agent toggle works")

    def test_agent_logs(self, auth_headers):
        """Test getting agent logs"""
        # Get first agent
        list_resp = requests.get(f"{BASE_URL}/api/agents", headers=auth_headers)
        agents = list_resp.json()

        if len(agents) > 0:
            agent_id = agents[0]["id"]
            response = requests.get(f"{BASE_URL}/api/agents/{agent_id}/logs", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert "agent_id" in data
            assert "lines" in data
            assert isinstance(data["lines"], list)
            print(f"✓ Agent logs returned {len(data['lines'])} lines")
        else:
            print("⚠ No agents to test logs")

    def test_delete_agent(self, auth_headers):
        """Test deleting an agent"""
        # Create agent
        create_resp = requests.post(
            f"{BASE_URL}/api/agents", headers=auth_headers, json={"name": "TEST_Delete", "role": "scraper"}
        )
        agent_id = create_resp.json()["id"]

        # Delete
        response = requests.delete(f"{BASE_URL}/api/agents/{agent_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["ok"] == True
        print("✓ Agent deleted")


class TestAIGeneration:
    """AI message generation tests"""

    def test_ai_generate_email(self, auth_headers):
        """Test AI generates email message"""
        payload = {
            "recipient_name": "John Smith",
            "company": "Acme Corp",
            "product": "ClawPilot outreach platform",
            "language": "en",
            "tone": "professional",
            "channel": "email",
            "goal": "book a demo call",
        }
        response = requests.post(f"{BASE_URL}/api/ai/generate", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()

        assert "subject" in data
        assert "body" in data
        assert "language" in data
        assert data["language"] == "en"
        assert len(data["body"]) > 0

        print(f"✓ AI generated email: subject='{data['subject'][:30]}...'")

    def test_ai_generate_whatsapp(self, auth_headers):
        """Test AI generates WhatsApp message"""
        payload = {
            "recipient_name": "Maria Garcia",
            "company": "Tech Startup",
            "product": "ClawPilot",
            "language": "en",
            "tone": "friendly",
            "channel": "whatsapp",
            "goal": "quick chat",
        }
        response = requests.post(f"{BASE_URL}/api/ai/generate", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()

        # WhatsApp should have null subject
        assert data["subject"] is None or data["subject"] == ""
        assert len(data["body"]) > 0

        print(f"✓ AI generated WhatsApp message: {len(data['body'])} chars")

    def test_ai_generate_multilang(self, auth_headers):
        """Test AI generates in different languages"""
        for lang in ["es", "fr", "de"]:
            payload = {
                "recipient_name": "Test User",
                "product": "ClawPilot",
                "language": lang,
                "tone": "professional",
                "channel": "email",
            }
            response = requests.post(f"{BASE_URL}/api/ai/generate", headers=auth_headers, json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["language"] == lang
            print(f"✓ AI generated message in {lang}")


class TestMessages:
    """Message sending tests"""

    def test_list_messages(self, auth_headers):
        """Test listing messages"""
        response = requests.get(f"{BASE_URL}/api/messages", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Listed {len(data)} messages")

    def test_send_email(self, auth_headers):
        """Test sending email (mock expected)"""
        payload = {"to": "test@example.com", "subject": "Test Email", "body": "This is a test email from ClawPilot."}
        response = requests.post(f"{BASE_URL}/api/messages/email", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()

        assert "message" in data
        assert "result" in data
        assert data["message"]["channel"] == "email"
        assert data["message"]["to"] == payload["to"]
        # Status should be sent or mock (mock expected due to unverified sender)
        assert data["result"]["status"] in ["sent", "mock"]

        print(f"✓ Email sent with status: {data['result']['status']}")

    def test_send_whatsapp(self, auth_headers):
        """Test sending WhatsApp (mock expected)"""
        payload = {"to": "+14155550123", "body": "Test WhatsApp message from ClawPilot"}
        response = requests.post(f"{BASE_URL}/api/messages/whatsapp", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()

        assert "message" in data
        assert "result" in data
        assert data["message"]["channel"] == "whatsapp"
        # Status should be mock (SK key provided, not AC Account SID)
        assert data["result"]["status"] in ["sent", "mock"]

        print(f"✓ WhatsApp sent with status: {data['result']['status']}")

    def test_filter_messages_by_channel(self, auth_headers):
        """Test filtering messages by channel"""
        response = requests.get(f"{BASE_URL}/api/messages", headers=auth_headers, params={"channel": "email"})
        assert response.status_code == 200
        data = response.json()
        for msg in data:
            assert msg["channel"] == "email"
        print("✓ Message filtering by channel works")


class TestSettings:
    """Settings endpoint tests"""

    def test_get_integrations(self, auth_headers):
        """Test getting integration settings"""
        response = requests.get(f"{BASE_URL}/api/settings/integrations", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "sendgrid_from_email" in data
        assert "twilio_whatsapp_from" in data
        assert "twilio_account_sid_configured" in data
        assert "sendgrid_configured" in data

        # Twilio should be false (SK key, not AC)
        assert data["twilio_account_sid_configured"] == False

        print(
            f"✓ Integration settings: SendGrid={data['sendgrid_configured']}, Twilio={data['twilio_account_sid_configured']}"
        )


class TestMultiTenancy:
    """Multi-tenancy isolation tests"""

    def test_data_isolation(self):
        """Test that different orgs don't see each other's data"""
        # Create two different users/orgs
        user1_email = f"tenant1_{uuid.uuid4().hex[:6]}@test.com"
        user2_email = f"tenant2_{uuid.uuid4().hex[:6]}@test.com"

        # Register user 1
        resp1 = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": user1_email,
                "password": "TestPass123!",
                "full_name": "Tenant One",
                "organization_name": "Org One",
            },
        )
        token1 = resp1.json()["access_token"]
        headers1 = {"Authorization": f"Bearer {token1}"}

        # Register user 2
        resp2 = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": user2_email,
                "password": "TestPass123!",
                "full_name": "Tenant Two",
                "organization_name": "Org Two",
            },
        )
        token2 = resp2.json()["access_token"]
        headers2 = {"Authorization": f"Bearer {token2}"}

        # Create a lead for user 1
        lead_resp = requests.post(
            f"{BASE_URL}/api/leads",
            headers=headers1,
            json={"full_name": "ISOLATION_TEST_Lead", "email": "isolation@test.com"},
        )
        lead_id = lead_resp.json()["id"]

        # User 1 should see the lead
        user1_leads = requests.get(f"{BASE_URL}/api/leads", headers=headers1).json()
        user1_lead_ids = [l["id"] for l in user1_leads]
        assert lead_id in user1_lead_ids, "User 1 should see their own lead"

        # User 2 should NOT see the lead
        user2_leads = requests.get(f"{BASE_URL}/api/leads", headers=headers2).json()
        user2_lead_ids = [l["id"] for l in user2_leads]
        assert lead_id not in user2_lead_ids, "User 2 should NOT see User 1's lead"

        print("✓ Multi-tenancy data isolation verified")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
