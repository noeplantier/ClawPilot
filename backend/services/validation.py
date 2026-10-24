def validate_email(email: str, lead: dict, campaign: dict):
    if email in SUPPRESSION_LIST:
        raise ValueError("Email is unsubscribed.")
    if not lead["email_verified"]:
        raise ValueError("Email is not verified.")
    if lead["consent_status"] != "active":
        raise ValueError("Consent status is not active.")
    if not campaign["active"]:
        raise ValueError("Campaign is not active.")