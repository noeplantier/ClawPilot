"""Which provider would carry a campaign and who may receive one through it (pure: no I/O)."""

from services.outreach_os import provider_policy as pp


def test_a_hostinger_mailbox_is_recognised_by_its_host_and_requires_an_opt_in():
    for host in ("smtp.hostinger.com", "SMTP.HOSTINGER.COM", "smtp.hostinger.fr", "smtp.titan.email", "titan.email"):
        info = pp.identify(smtp_host=host, sendgrid_configured=False)
        assert info.id == "smtp_hostinger" and info.cold_outreach == pp.OPT_IN_REQUIRED, host
        assert "quota" in info.restriction and "autorisation" in info.restriction  # a quota is not an authorization


def test_another_smtp_host_or_sendgrid_is_reported_unverified_not_blocked_on_a_guess():
    smtp = pp.identify(smtp_host="mail.example.org", sendgrid_configured=True)
    assert (smtp.id, smtp.cold_outreach, smtp.host) == ("smtp", pp.UNVERIFIED, "mail.example.org")
    assert "mail.example.org" in smtp.restriction
    grid = pp.identify(smtp_host=None, sendgrid_configured=True)
    assert (grid.id, grid.cold_outreach) == ("sendgrid", pp.UNVERIFIED)
    none = pp.identify(smtp_host=None, sendgrid_configured=False)
    assert (none.id, none.cold_outreach) == ("none", pp.NOT_CONFIGURED)


def test_through_hostinger_only_an_opt_in_counts_a_scraped_contact_is_not_authorized():
    info = pp.identify(smtp_host="smtp.hostinger.com", sendgrid_configured=False)
    scraped = pp.authorize(info, consent_status="unknown", legal_basis=None)
    assert (
        scraped.ok is False
        and scraped.code == "provider_requires_opt_in"
        and scraped.basis == pp.BASIS_PUBLIC_DIRECTORY
    )
    b2b = pp.authorize(info, consent_status="unknown", legal_basis="legitimate_interest_b2b")
    assert b2b.ok is False  # a declared legitimate interest is not an opt-in
    assert pp.authorize(info, consent_status="opted_in", legal_basis=None).ok is True
    declared = pp.authorize(info, consent_status="unknown", legal_basis="consent")
    assert declared.ok is True and declared.basis == pp.BASIS_DECLARED_CONSENT
    assert pp.authorize(info, consent_status="opted_out", legal_basis="consent").ok is True  # opt-outs are another gate


def test_an_unverified_provider_does_not_block_but_still_says_what_the_authorization_rests_on():
    info = pp.identify(smtp_host="mail.example.org", sendgrid_configured=False)
    result = pp.authorize(info, consent_status="unknown", legal_basis=None)
    assert result.ok is True and "annuaire public" in result.label


def test_the_legal_basis_of_a_supplied_list_is_read_from_its_licence_note():
    notes = ["ODbL", "Supplied list: Salon 2026 — legal basis: legitimate_interest_b2b"]
    assert pp.legal_basis_of(notes) == "legitimate_interest_b2b"
    assert pp.legal_basis_of(["Supplied list: x — legal basis: consent", None]) == "consent"
    assert pp.legal_basis_of(["ODbL", None]) is None
    assert pp.legal_basis_of([]) is None
