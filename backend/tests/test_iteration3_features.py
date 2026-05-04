"""
OpenClaw SaaS Platform - Iteration 3 Feature Tests
Tests: Bulk Delete, Bulk Tag, CSV Upload, Campaign Schedule, Webhooks (SendGrid/Twilio)
"""
import pytest
import requests
import os
import uuid
import time
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Demo credentials (pre-seeded)
DEMO_EMAIL = "demo@openclaw.io"
DEMO_PASSWORD = "Demo12345!"


@pytest.fixture(scope="module")
def auth_token():
    """Get auth token for authenticated tests"""
    # Ensure demo user exists
    requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": DEMO_EMAIL,
        "password": DEMO_PASSWORD,
        "full_name": "Demo User",
        "organization_name": "OpenClaw Demo"
    })
    
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": DEMO_EMAIL,
        "password": DEMO_PASSWORD
    })
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get auth headers for authenticated tests"""
    return {"Authorization": f"Bearer {auth_token}"}


# ============================================================================
# BULK DELETE TESTS
# ============================================================================
class TestBulkDelete:
    """Tests for POST /api/leads/bulk-delete endpoint"""
    
    def test_bulk_delete_leads(self, auth_headers):
        """Test bulk deleting multiple leads"""
        unique_id = uuid.uuid4().hex[:6]
        
        # Create leads first
        leads = [
            {"full_name": f"TEST_Delete1_{unique_id}", "email": f"del1_{unique_id}@test.com"},
            {"full_name": f"TEST_Delete2_{unique_id}", "email": f"del2_{unique_id}@test.com"},
            {"full_name": f"TEST_Delete3_{unique_id}", "email": f"del3_{unique_id}@test.com"},
        ]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        assert bulk_resp.status_code == 200
        lead_ids = bulk_resp.json()["lead_ids"]
        assert len(lead_ids) == 3
        
        # Bulk delete
        response = requests.post(
            f"{BASE_URL}/api/leads/bulk-delete",
            headers=auth_headers,
            json={"lead_ids": lead_ids}
        )
        assert response.status_code == 200, f"Bulk delete failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "deleted" in data
        assert data["deleted"] == 3
        
        # Verify leads are actually deleted
        leads_resp = requests.get(f"{BASE_URL}/api/leads", headers=auth_headers)
        remaining_ids = [l["id"] for l in leads_resp.json()]
        for lid in lead_ids:
            assert lid not in remaining_ids, f"Lead {lid} should have been deleted"
        
        print(f"✓ Bulk deleted {data['deleted']} leads")
    
    def test_bulk_delete_empty_list(self, auth_headers):
        """Test bulk delete with empty list"""
        response = requests.post(
            f"{BASE_URL}/api/leads/bulk-delete",
            headers=auth_headers,
            json={"lead_ids": []}
        )
        assert response.status_code == 200
        assert response.json()["deleted"] == 0
        print("✓ Bulk delete handles empty list")
    
    def test_bulk_delete_nonexistent_ids(self, auth_headers):
        """Test bulk delete with non-existent IDs"""
        response = requests.post(
            f"{BASE_URL}/api/leads/bulk-delete",
            headers=auth_headers,
            json={"lead_ids": ["fake-id-1", "fake-id-2"]}
        )
        assert response.status_code == 200
        assert response.json()["deleted"] == 0
        print("✓ Bulk delete handles non-existent IDs gracefully")


# ============================================================================
# BULK TAG TESTS
# ============================================================================
class TestBulkTag:
    """Tests for POST /api/leads/bulk-tag endpoint"""
    
    def test_bulk_tag_add_mode(self, auth_headers):
        """Test bulk adding tags to leads"""
        unique_id = uuid.uuid4().hex[:6]
        
        # Create leads
        leads = [
            {"full_name": f"TEST_Tag1_{unique_id}", "email": f"tag1_{unique_id}@test.com", "tags": ["existing"]},
            {"full_name": f"TEST_Tag2_{unique_id}", "email": f"tag2_{unique_id}@test.com"},
        ]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        lead_ids = bulk_resp.json()["lead_ids"]
        
        # Bulk add tags
        response = requests.post(
            f"{BASE_URL}/api/leads/bulk-tag",
            headers=auth_headers,
            json={"lead_ids": lead_ids, "tags": ["vip", "q2"], "mode": "add"}
        )
        assert response.status_code == 200, f"Bulk tag failed: {response.text}"
        data = response.json()
        
        assert "updated" in data
        assert data["updated"] == 2
        
        # Verify tags were added (not replaced)
        leads_resp = requests.get(f"{BASE_URL}/api/leads", headers=auth_headers)
        for lead in leads_resp.json():
            if lead["id"] in lead_ids:
                assert "vip" in lead.get("tags", [])
                assert "q2" in lead.get("tags", [])
        
        print(f"✓ Bulk tag (add mode): {data['updated']} leads updated")
    
    def test_bulk_tag_replace_mode(self, auth_headers):
        """Test bulk replacing tags on leads"""
        unique_id = uuid.uuid4().hex[:6]
        
        # Create leads with existing tags
        leads = [
            {"full_name": f"TEST_Replace1_{unique_id}", "email": f"rep1_{unique_id}@test.com", "tags": ["old1", "old2"]},
            {"full_name": f"TEST_Replace2_{unique_id}", "email": f"rep2_{unique_id}@test.com", "tags": ["old3"]},
        ]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        lead_ids = bulk_resp.json()["lead_ids"]
        
        # Bulk replace tags
        response = requests.post(
            f"{BASE_URL}/api/leads/bulk-tag",
            headers=auth_headers,
            json={"lead_ids": lead_ids, "tags": ["new1", "new2"], "mode": "replace"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["updated"] == 2
        
        # Verify tags were replaced
        leads_resp = requests.get(f"{BASE_URL}/api/leads", headers=auth_headers)
        for lead in leads_resp.json():
            if lead["id"] in lead_ids:
                assert lead.get("tags") == ["new1", "new2"], f"Tags should be replaced, got {lead.get('tags')}"
        
        print("✓ Bulk tag (replace mode) works correctly")


# ============================================================================
# CSV UPLOAD TESTS
# ============================================================================
class TestCSVUpload:
    """Tests for POST /api/leads/upload-csv endpoint"""
    
    def test_csv_upload_basic(self, auth_headers):
        """Test basic CSV upload with header row"""
        unique_id = uuid.uuid4().hex[:6]
        csv_content = f"""full_name,email,company,title,country
TEST_CSV1_{unique_id},csv1_{unique_id}@test.com,CSV Corp,CEO,US
TEST_CSV2_{unique_id},csv2_{unique_id}@test.com,CSV Inc,CTO,UK
TEST_CSV3_{unique_id},csv3_{unique_id}@test.com,CSV Ltd,VP,DE"""
        
        files = {"file": ("leads.csv", csv_content, "text/csv")}
        response = requests.post(
            f"{BASE_URL}/api/leads/upload-csv",
            headers=auth_headers,
            files=files
        )
        assert response.status_code == 200, f"CSV upload failed: {response.text}"
        data = response.json()
        
        # Verify response structure (same as BulkLeadsOut)
        assert "created" in data
        assert "skipped" in data
        assert "errors" in data
        assert "lead_ids" in data
        
        assert data["created"] == 3
        assert len(data["lead_ids"]) == 3
        
        print(f"✓ CSV upload: {data['created']} leads created")
    
    def test_csv_upload_with_tags(self, auth_headers):
        """Test CSV upload with comma-separated tags"""
        unique_id = uuid.uuid4().hex[:6]
        csv_content = f"""name,email,tags,source
TEST_CSVTag_{unique_id},csvtag_{unique_id}@test.com,"vip,enterprise,q2",csv_upload"""
        
        files = {"file": ("leads.csv", csv_content, "text/csv")}
        response = requests.post(
            f"{BASE_URL}/api/leads/upload-csv",
            headers=auth_headers,
            files=files
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["created"] == 1
        
        # Verify tags were parsed
        leads_resp = requests.get(f"{BASE_URL}/api/leads", headers=auth_headers)
        lead = next((l for l in leads_resp.json() if l["id"] == data["lead_ids"][0]), None)
        assert lead is not None
        assert "vip" in lead.get("tags", [])
        assert "enterprise" in lead.get("tags", [])
        
        print("✓ CSV upload correctly parses comma-separated tags")
    
    def test_csv_upload_deduplication(self, auth_headers):
        """Test CSV upload deduplicates by email"""
        unique_id = uuid.uuid4().hex[:6]
        email = f"csvdedup_{unique_id}@test.com"
        
        # First upload
        csv1 = f"full_name,email\nTEST_CSVDedup1_{unique_id},{email}"
        files1 = {"file": ("leads.csv", csv1, "text/csv")}
        resp1 = requests.post(f"{BASE_URL}/api/leads/upload-csv", headers=auth_headers, files=files1)
        assert resp1.status_code == 200
        assert resp1.json()["created"] == 1
        
        # Second upload with same email
        csv2 = f"full_name,email\nTEST_CSVDedup2_{unique_id},{email}"
        files2 = {"file": ("leads.csv", csv2, "text/csv")}
        resp2 = requests.post(f"{BASE_URL}/api/leads/upload-csv", headers=auth_headers, files=files2)
        assert resp2.status_code == 200
        data = resp2.json()
        
        assert data["created"] == 0
        assert data["skipped"] == 1
        
        print("✓ CSV upload correctly deduplicates by email")
    
    def test_csv_upload_no_header(self, auth_headers):
        """Test CSV upload fails without header row"""
        # Empty file
        files = {"file": ("leads.csv", "", "text/csv")}
        response = requests.post(
            f"{BASE_URL}/api/leads/upload-csv",
            headers=auth_headers,
            files=files
        )
        assert response.status_code == 400
        assert "header" in response.json()["detail"].lower()
        print("✓ CSV upload correctly rejects file without header")


# ============================================================================
# CAMPAIGN SCHEDULE TESTS
# ============================================================================
class TestCampaignSchedule:
    """Tests for campaign scheduling endpoints"""
    
    def test_schedule_campaign(self, auth_headers):
        """Test POST /api/campaigns/{id}/schedule"""
        unique_id = uuid.uuid4().hex[:6]
        
        # Create campaign with steps
        campaign_resp = requests.post(
            f"{BASE_URL}/api/campaigns",
            headers=auth_headers,
            json={
                "name": f"TEST_Schedule_{unique_id}",
                "goal": "Test scheduling",
                "channels": ["email"],
                "steps": [
                    {"channel": "email", "delay_hours": 0, "subject": "Step 1", "body": "Hello {{first_name}}", "language": "en"},
                    {"channel": "email", "delay_hours": 24, "subject": "Step 2", "body": "Follow up {{first_name}}", "language": "en"},
                ]
            }
        )
        campaign_id = campaign_resp.json()["id"]
        
        # Create and assign leads
        leads = [
            {"full_name": f"TEST_Sched1_{unique_id}", "email": f"sched1_{unique_id}@test.com"},
            {"full_name": f"TEST_Sched2_{unique_id}", "email": f"sched2_{unique_id}@test.com"},
        ]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        lead_ids = bulk_resp.json()["lead_ids"]
        
        requests.post(f"{BASE_URL}/api/campaigns/{campaign_id}/assign-leads", headers=auth_headers, json={"lead_ids": lead_ids})
        
        # Schedule campaign
        response = requests.post(
            f"{BASE_URL}/api/campaigns/{campaign_id}/schedule",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Schedule failed: {response.text}"
        data = response.json()
        
        # Verify response
        assert "scheduled" in data
        assert "steps" in data
        assert "leads" in data
        
        # 2 steps × 2 leads = 4 jobs
        assert data["scheduled"] == 4
        assert data["steps"] == 2
        assert data["leads"] == 2
        
        # Verify campaign status changed to running
        camp_resp = requests.get(f"{BASE_URL}/api/campaigns/{campaign_id}", headers=auth_headers)
        assert camp_resp.json()["status"] == "running"
        
        print(f"✓ Scheduled {data['scheduled']} jobs ({data['steps']} steps × {data['leads']} leads)")
    
    def test_schedule_no_leads_error(self, auth_headers):
        """Test schedule fails when no leads assigned"""
        unique_id = uuid.uuid4().hex[:6]
        
        # Create campaign with steps but no leads
        campaign_resp = requests.post(
            f"{BASE_URL}/api/campaigns",
            headers=auth_headers,
            json={
                "name": f"TEST_NoLeadsSched_{unique_id}",
                "goal": "Test",
                "steps": [{"channel": "email", "delay_hours": 0, "subject": "Test", "body": "Test", "language": "en"}]
            }
        )
        campaign_id = campaign_resp.json()["id"]
        
        # Try to schedule
        response = requests.post(
            f"{BASE_URL}/api/campaigns/{campaign_id}/schedule",
            headers=auth_headers
        )
        assert response.status_code == 400
        assert "no leads" in response.json()["detail"].lower() or "error" in response.json()
        print("✓ Schedule correctly fails when no leads assigned")
    
    def test_schedule_no_steps_error(self, auth_headers):
        """Test schedule fails when no steps defined"""
        unique_id = uuid.uuid4().hex[:6]
        
        # Create campaign without steps
        campaign_resp = requests.post(
            f"{BASE_URL}/api/campaigns",
            headers=auth_headers,
            json={"name": f"TEST_NoStepsSched_{unique_id}", "goal": "Test"}
        )
        campaign_id = campaign_resp.json()["id"]
        
        # Create and assign a lead
        leads = [{"full_name": f"TEST_NoStep_{unique_id}", "email": f"nostep_{unique_id}@test.com"}]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        lead_ids = bulk_resp.json()["lead_ids"]
        requests.post(f"{BASE_URL}/api/campaigns/{campaign_id}/assign-leads", headers=auth_headers, json={"lead_ids": lead_ids})
        
        # Try to schedule
        response = requests.post(
            f"{BASE_URL}/api/campaigns/{campaign_id}/schedule",
            headers=auth_headers
        )
        assert response.status_code == 400
        print("✓ Schedule correctly fails when no steps defined")
    
    def test_get_schedule_status(self, auth_headers):
        """Test GET /api/campaigns/{id}/schedule"""
        unique_id = uuid.uuid4().hex[:6]
        
        # Create and schedule a campaign
        campaign_resp = requests.post(
            f"{BASE_URL}/api/campaigns",
            headers=auth_headers,
            json={
                "name": f"TEST_GetSched_{unique_id}",
                "goal": "Test",
                "steps": [{"channel": "email", "delay_hours": 0, "subject": "Test", "body": "Hi", "language": "en"}]
            }
        )
        campaign_id = campaign_resp.json()["id"]
        
        leads = [{"full_name": f"TEST_GetS_{unique_id}", "email": f"gets_{unique_id}@test.com"}]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        lead_ids = bulk_resp.json()["lead_ids"]
        requests.post(f"{BASE_URL}/api/campaigns/{campaign_id}/assign-leads", headers=auth_headers, json={"lead_ids": lead_ids})
        requests.post(f"{BASE_URL}/api/campaigns/{campaign_id}/schedule", headers=auth_headers)
        
        # Get schedule status
        response = requests.get(
            f"{BASE_URL}/api/campaigns/{campaign_id}/schedule",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Get schedule failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "jobs" in data
        assert "counts" in data
        assert "total" in data
        
        assert "pending" in data["counts"]
        assert "running" in data["counts"]
        assert "done" in data["counts"]
        assert "failed" in data["counts"]
        
        print(f"✓ Get schedule: {data['total']} jobs, counts={data['counts']}")
    
    def test_cancel_schedule(self, auth_headers):
        """Test POST /api/campaigns/{id}/cancel-schedule"""
        unique_id = uuid.uuid4().hex[:6]
        
        # Create and schedule a campaign with future delay
        campaign_resp = requests.post(
            f"{BASE_URL}/api/campaigns",
            headers=auth_headers,
            json={
                "name": f"TEST_Cancel_{unique_id}",
                "goal": "Test",
                "steps": [{"channel": "email", "delay_hours": 100, "subject": "Test", "body": "Hi", "language": "en"}]
            }
        )
        campaign_id = campaign_resp.json()["id"]
        
        leads = [{"full_name": f"TEST_Can_{unique_id}", "email": f"can_{unique_id}@test.com"}]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        lead_ids = bulk_resp.json()["lead_ids"]
        requests.post(f"{BASE_URL}/api/campaigns/{campaign_id}/assign-leads", headers=auth_headers, json={"lead_ids": lead_ids})
        requests.post(f"{BASE_URL}/api/campaigns/{campaign_id}/schedule", headers=auth_headers)
        
        # Cancel schedule
        response = requests.post(
            f"{BASE_URL}/api/campaigns/{campaign_id}/cancel-schedule",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Cancel failed: {response.text}"
        data = response.json()
        
        assert "cancelled" in data
        assert data["cancelled"] >= 1
        
        # Verify jobs are cancelled
        sched_resp = requests.get(f"{BASE_URL}/api/campaigns/{campaign_id}/schedule", headers=auth_headers)
        assert sched_resp.json()["counts"]["pending"] == 0
        
        print(f"✓ Cancelled {data['cancelled']} pending jobs")


# ============================================================================
# SENDGRID WEBHOOK TESTS (PUBLIC - NO AUTH)
# ============================================================================
class TestSendGridWebhook:
    """Tests for POST /api/webhooks/sendgrid endpoint (public)"""
    
    def test_sendgrid_webhook_delivered(self, auth_headers):
        """Test SendGrid delivered event"""
        # First create a message to update
        unique_id = uuid.uuid4().hex[:6]
        
        # Create lead and send email to get a message
        leads = [{"full_name": f"TEST_SG_{unique_id}", "email": f"sg_{unique_id}@test.com"}]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        lead_ids = bulk_resp.json()["lead_ids"]
        
        # Send email to create message
        requests.post(
            f"{BASE_URL}/api/messages/email/batch",
            headers=auth_headers,
            json={"lead_ids": lead_ids, "subject": "Test", "body": "Test body"}
        )
        
        # Send webhook event (no auth required)
        events = [
            {"event": "delivered", "sg_message_id": f"test-{unique_id}.filter.1234", "timestamp": 1234567890}
        ]
        response = requests.post(f"{BASE_URL}/api/webhooks/sendgrid", json=events)
        assert response.status_code == 200, f"Webhook failed: {response.text}"
        data = response.json()
        
        assert data["ok"] == True
        assert "processed" in data
        assert "total" in data
        
        print(f"✓ SendGrid webhook: processed={data['processed']}, total={data['total']}")
    
    def test_sendgrid_webhook_open_click(self):
        """Test SendGrid open/click events"""
        events = [
            {"event": "open", "sg_message_id": "test-open-123", "timestamp": 1234567890},
            {"event": "click", "sg_message_id": "test-click-456", "timestamp": 1234567891},
        ]
        response = requests.post(f"{BASE_URL}/api/webhooks/sendgrid", json=events)
        assert response.status_code == 200
        assert response.json()["ok"] == True
        print("✓ SendGrid webhook handles open/click events")
    
    def test_sendgrid_webhook_bounce_spam(self):
        """Test SendGrid bounce/spam events"""
        events = [
            {"event": "bounce", "sg_message_id": "test-bounce-123"},
            {"event": "spamreport", "sg_message_id": "test-spam-456"},
            {"event": "dropped", "sg_message_id": "test-drop-789"},
        ]
        response = requests.post(f"{BASE_URL}/api/webhooks/sendgrid", json=events)
        assert response.status_code == 200
        assert response.json()["ok"] == True
        print("✓ SendGrid webhook handles bounce/spam/dropped events")
    
    def test_sendgrid_webhook_invalid_json(self):
        """Test SendGrid webhook with invalid JSON"""
        response = requests.post(
            f"{BASE_URL}/api/webhooks/sendgrid",
            data="not json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200  # Returns ok:false, not 400
        assert response.json()["ok"] == False
        print("✓ SendGrid webhook handles invalid JSON gracefully")


# ============================================================================
# TWILIO WEBHOOK TESTS (PUBLIC - NO AUTH, FORM-ENCODED)
# ============================================================================
class TestTwilioWebhook:
    """Tests for POST /api/webhooks/twilio endpoint (public, form-encoded)"""
    
    def test_twilio_webhook_status_callback(self):
        """Test Twilio status callback (delivered)"""
        form_data = {
            "MessageSid": "SM123456789",
            "MessageStatus": "delivered",
            "To": "whatsapp:+14155550123",
            "From": "whatsapp:+14155238886",
        }
        response = requests.post(
            f"{BASE_URL}/api/webhooks/twilio",
            data=form_data
        )
        assert response.status_code == 200, f"Webhook failed: {response.text}"
        data = response.json()
        
        assert data["ok"] == True
        print(f"✓ Twilio webhook status callback: kind={data.get('kind')}")
    
    def test_twilio_webhook_read_status(self):
        """Test Twilio read status (maps to opened)"""
        form_data = {
            "MessageSid": "SM987654321",
            "MessageStatus": "read",
        }
        response = requests.post(f"{BASE_URL}/api/webhooks/twilio", data=form_data)
        assert response.status_code == 200
        assert response.json()["ok"] == True
        print("✓ Twilio webhook handles read status")
    
    def test_twilio_webhook_inbound_message(self, auth_headers):
        """Test Twilio inbound message (user reply)"""
        unique_id = uuid.uuid4().hex[:6]
        phone = f"+1415555{unique_id[:4]}"
        
        # Create lead with phone
        leads = [{"full_name": f"TEST_TW_{unique_id}", "email": f"tw_{unique_id}@test.com", "phone": phone}]
        requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        
        # Simulate inbound message
        form_data = {
            "MessageSid": f"SM-inbound-{unique_id}",
            "Body": "Thanks for reaching out!",
            "From": f"whatsapp:{phone}",
            "To": "whatsapp:+14155238886",
        }
        response = requests.post(f"{BASE_URL}/api/webhooks/twilio", data=form_data)
        assert response.status_code == 200
        data = response.json()
        
        assert data["ok"] == True
        assert data["kind"] == "inbound"
        
        print("✓ Twilio webhook handles inbound messages")
    
    def test_twilio_webhook_failed_status(self):
        """Test Twilio failed/undelivered status"""
        form_data = {
            "MessageSid": "SM-failed-123",
            "MessageStatus": "failed",
        }
        response = requests.post(f"{BASE_URL}/api/webhooks/twilio", data=form_data)
        assert response.status_code == 200
        assert response.json()["ok"] == True
        
        form_data2 = {
            "MessageSid": "SM-undelivered-456",
            "MessageStatus": "undelivered",
        }
        response2 = requests.post(f"{BASE_URL}/api/webhooks/twilio", data=form_data2)
        assert response2.status_code == 200
        
        print("✓ Twilio webhook handles failed/undelivered status")


# ============================================================================
# REGRESSION TESTS - Verify existing endpoints still work
# ============================================================================
class TestRegressionEndpoints:
    """Regression tests for existing endpoints"""
    
    def test_root_endpoint(self):
        """Test root API endpoint still works"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        assert response.json()["service"] == "openclaw"
        print("✓ Root endpoint working")
    
    def test_health_endpoint(self):
        """Test health check still works"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("✓ Health endpoint working")
    
    def test_login_works(self):
        """Test login still works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD
        })
        assert response.status_code == 200
        assert "access_token" in response.json()
        print("✓ Login working")
    
    def test_leads_crud(self, auth_headers):
        """Test leads CRUD still works"""
        unique_id = uuid.uuid4().hex[:6]
        
        # Create
        resp = requests.post(f"{BASE_URL}/api/leads", headers=auth_headers, json={
            "full_name": f"TEST_Reg_{unique_id}", "email": f"reg_{unique_id}@test.com"
        })
        assert resp.status_code == 200
        lead_id = resp.json()["id"]
        
        # List
        resp = requests.get(f"{BASE_URL}/api/leads", headers=auth_headers)
        assert resp.status_code == 200
        
        # Update
        resp = requests.patch(f"{BASE_URL}/api/leads/{lead_id}", headers=auth_headers, json={"stage": "qualified"})
        assert resp.status_code == 200
        
        # Delete
        resp = requests.delete(f"{BASE_URL}/api/leads/{lead_id}", headers=auth_headers)
        assert resp.status_code == 200
        
        print("✓ Leads CRUD working")
    
    def test_campaigns_crud(self, auth_headers):
        """Test campaigns CRUD still works"""
        unique_id = uuid.uuid4().hex[:6]
        
        # Create
        resp = requests.post(f"{BASE_URL}/api/campaigns", headers=auth_headers, json={
            "name": f"TEST_RegCamp_{unique_id}", "goal": "Test"
        })
        assert resp.status_code == 200
        camp_id = resp.json()["id"]
        
        # List
        resp = requests.get(f"{BASE_URL}/api/campaigns", headers=auth_headers)
        assert resp.status_code == 200
        
        # Get
        resp = requests.get(f"{BASE_URL}/api/campaigns/{camp_id}", headers=auth_headers)
        assert resp.status_code == 200
        
        # Update
        resp = requests.patch(f"{BASE_URL}/api/campaigns/{camp_id}", headers=auth_headers, json={"status": "paused"})
        assert resp.status_code == 200
        
        # Delete
        resp = requests.delete(f"{BASE_URL}/api/campaigns/{camp_id}", headers=auth_headers)
        assert resp.status_code == 200
        
        print("✓ Campaigns CRUD working")
    
    def test_bulk_leads_still_works(self, auth_headers):
        """Test bulk leads import still works"""
        unique_id = uuid.uuid4().hex[:6]
        leads = [{"full_name": f"TEST_BulkReg_{unique_id}", "email": f"bulkreg_{unique_id}@test.com"}]
        resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        assert resp.status_code == 200
        assert resp.json()["created"] == 1
        print("✓ Bulk leads import working")
    
    def test_bulk_stage_still_works(self, auth_headers):
        """Test bulk stage update still works"""
        unique_id = uuid.uuid4().hex[:6]
        leads = [{"full_name": f"TEST_StageReg_{unique_id}", "email": f"stagereg_{unique_id}@test.com"}]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        lead_ids = bulk_resp.json()["lead_ids"]
        
        resp = requests.post(f"{BASE_URL}/api/leads/bulk-stage", headers=auth_headers, json={
            "lead_ids": lead_ids, "stage": "engaged"
        })
        assert resp.status_code == 200
        assert resp.json()["updated"] == 1
        print("✓ Bulk stage update working")
    
    def test_batch_email_still_works(self, auth_headers):
        """Test batch email still works"""
        unique_id = uuid.uuid4().hex[:6]
        leads = [{"full_name": f"TEST_BatchReg_{unique_id}", "email": f"batchreg_{unique_id}@test.com"}]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        lead_ids = bulk_resp.json()["lead_ids"]
        
        resp = requests.post(f"{BASE_URL}/api/messages/email/batch", headers=auth_headers, json={
            "lead_ids": lead_ids, "subject": "Test", "body": "Hi {{first_name}}"
        })
        assert resp.status_code == 200
        print("✓ Batch email working")
    
    def test_campaign_assign_leads_still_works(self, auth_headers):
        """Test campaign assign leads still works"""
        unique_id = uuid.uuid4().hex[:6]
        
        # Create campaign
        camp_resp = requests.post(f"{BASE_URL}/api/campaigns", headers=auth_headers, json={
            "name": f"TEST_AssignReg_{unique_id}", "goal": "Test"
        })
        camp_id = camp_resp.json()["id"]
        
        # Create leads
        leads = [{"full_name": f"TEST_AssReg_{unique_id}", "email": f"assreg_{unique_id}@test.com"}]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        lead_ids = bulk_resp.json()["lead_ids"]
        
        # Assign
        resp = requests.post(f"{BASE_URL}/api/campaigns/{camp_id}/assign-leads", headers=auth_headers, json={
            "lead_ids": lead_ids
        })
        assert resp.status_code == 200
        assert len(resp.json()["lead_ids"]) == 1
        print("✓ Campaign assign leads working")
    
    def test_campaign_run_step_still_works(self, auth_headers):
        """Test campaign run step still works"""
        unique_id = uuid.uuid4().hex[:6]
        
        # Create campaign with step
        camp_resp = requests.post(f"{BASE_URL}/api/campaigns", headers=auth_headers, json={
            "name": f"TEST_RunReg_{unique_id}",
            "goal": "Test",
            "steps": [{"channel": "email", "delay_hours": 0, "subject": "Test", "body": "Hi", "language": "en"}]
        })
        camp_id = camp_resp.json()["id"]
        
        # Create and assign leads
        leads = [{"full_name": f"TEST_RunReg_{unique_id}", "email": f"runreg_{unique_id}@test.com"}]
        bulk_resp = requests.post(f"{BASE_URL}/api/leads/bulk", headers=auth_headers, json={"leads": leads})
        lead_ids = bulk_resp.json()["lead_ids"]
        requests.post(f"{BASE_URL}/api/campaigns/{camp_id}/assign-leads", headers=auth_headers, json={"lead_ids": lead_ids})
        
        # Run step
        resp = requests.post(f"{BASE_URL}/api/campaigns/{camp_id}/run-step/0", headers=auth_headers)
        assert resp.status_code == 200
        assert "dispatched" in resp.json()
        print("✓ Campaign run step working")
    
    def test_ai_generate_still_works(self, auth_headers):
        """Test AI generate still works"""
        resp = requests.post(f"{BASE_URL}/api/ai/generate", headers=auth_headers, json={
            "recipient_name": "Test",
            "product": "OpenClaw",
            "language": "en",
            "tone": "professional",
            "channel": "email"
        })
        assert resp.status_code == 200
        assert "body" in resp.json()
        print("✓ AI generate working")
    
    def test_analytics_still_works(self, auth_headers):
        """Test analytics endpoints still work"""
        resp = requests.get(f"{BASE_URL}/api/analytics/overview", headers=auth_headers)
        assert resp.status_code == 200
        assert "totals" in resp.json()
        
        resp = requests.get(f"{BASE_URL}/api/analytics/activity", headers=auth_headers)
        assert resp.status_code == 200
        
        print("✓ Analytics working")
    
    def test_unauthorized_returns_401(self):
        """Test unauthorized requests return 401"""
        response = requests.get(f"{BASE_URL}/api/leads")
        assert response.status_code == 401
        print("✓ Unauthorized correctly returns 401")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
