from datetime import datetime

AUDIT_LOGS = []

def log_email_action(lead_id, campaign_id, provider, template, status, error, message_id):
    AUDIT_LOGS.append({
        "lead_id": lead_id,
        "campaign_id": campaign_id,
        "provider": provider,
        "template": template,
        "status": status,
        "error": error,
        "message_id": message_id,
        "sent_at": datetime.utcnow(),
    })