"""The integration catalogue: pure, offline. Statuses follow the facts, and only variable names are ever exposed."""

import pytest

from services.integrations_status import GROUPS, STATUSES, TESTABLE, TRACKED_ENV, Facts, build


def by_id(facts: Facts) -> dict:
    return {i["id"]: i for i in build(facts)["items"]}


NOTHING = Facts(
    database_ok=True,
    database_latency_ms=12,
    database_kind="supabase_session_pooler",
    database_port="5432",
    overpass_hosts=("a.example", "b.example"),
    ai={"key_configured": False, "provider": None, "active": False, "reason": "AI_PROVIDER is not set"},
)


def test_every_entry_has_a_known_group_status_and_unique_id():
    items = build(NOTHING)["items"]
    assert len({i["id"] for i in items}) == len(items) == build(NOTHING)["total"]
    assert {i["group"] for i in items} <= set(GROUPS)
    assert {i["status"] for i in items} <= set(STATUSES)
    assert sum(build(NOTHING)["counts"].values()) == len(items)
    assert {i["id"] for i in items if i["test"] == "server"} <= set(TESTABLE)
    assert {i["id"] for i in items if i["test"] == "browser"} == {"geocoder"}


def test_variables_named_by_an_entry_are_all_tracked():
    for item in build(NOTHING)["items"]:
        assert set(item["env"]) <= set(TRACKED_ENV), item["id"]
        assert set(item["needs"]) <= set(item["env"]) | {"FEATURE_EXTERNAL_SOURCES"}, item["id"]


def test_a_bare_server_reports_what_is_missing_and_fakes_nothing():
    items = by_id(NOTHING)
    assert items["ai"]["status"] == "missing" and items["ai"]["label"] == "OFF · NOTHING IS GENERATED"
    assert items["ai"]["needs"] == ["AI_PROVIDER", "AI_API_KEY"] and items["ai"]["test"] == "server"
    assert items["smtp"]["status"] == "missing" and items["smtp"]["needs"] == [
        "SMTP_HOST",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
    ]
    assert items["sendgrid"]["status"] == "missing" and "NOTHING IS SENT" in items["sendgrid"]["label"]
    assert items["twilio"]["status"] == "missing" and items["twilio"]["needs"] == [
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
    ]
    assert items["sender"]["status"] == "missing" and len(items["sender"]["needs"]) == 4
    assert items["sending_mode"]["status"] == "off" and "DRY-RUN" in items["sending_mode"]["label"]
    assert items["registry"]["status"] == "off"
    assert items["database"]["status"] == "ready"
    assert all(
        i["status"] != "ready"
        for i in items.values()
        if i["id"] in {"smtp", "imap", "sendgrid", "twilio", "ai", "sender"}
    )


def test_webhook_signatures_are_not_demanded_before_their_provider_exists():
    items = by_id(NOTHING)
    assert items["twilio_webhook"]["status"] == "off" and items["sendgrid_webhook"]["status"] == "off"
    items = by_id(
        Facts(
            **{
                **NOTHING.__dict__,
                "twilio_configured": True,
                "twilio_signature_ready": True,
                "env_set": frozenset({"TWILIO_AUTH_TOKEN"}),
            }
        )
    )
    assert items["twilio_webhook"]["status"] == "partial" and items["twilio_webhook"]["needs"] == ["TWILIO_WEBHOOK_URL"]
    items = by_id(
        Facts(
            **{
                **NOTHING.__dict__,
                "twilio_configured": True,
                "twilio_signature_ready": True,
                "env_set": frozenset({"TWILIO_AUTH_TOKEN", "TWILIO_WEBHOOK_URL"}),
            }
        )
    )
    assert items["twilio_webhook"]["status"] == "ready"
    items = by_id(Facts(**{**NOTHING.__dict__, "sendgrid_configured": True}))
    assert items["sendgrid_webhook"]["status"] == "partial" and items["sendgrid_webhook"]["needs"] == [
        "SENDGRID_WEBHOOK_PUBLIC_KEY"
    ]


def test_configured_testable_services_are_unchecked_until_a_test_proves_them():
    facts = Facts(
        **{
            **NOTHING.__dict__,
            "smtp_configured": True,
            "smtp_host": "smtp.example",
            "imap_configured": True,
            "imap_host": "imap.example",
            "sendgrid_configured": True,
            "twilio_configured": True,
        }
    )
    items = by_id(facts)
    for name in ("smtp", "imap", "sendgrid", "twilio"):
        assert items[name]["status"] == "unchecked" and items[name]["test"] == "server"
    assert items["smtp"]["needs"] == []


def test_a_set_but_unusable_smtp_is_reported_with_the_missing_names():
    facts = Facts(**{**NOTHING.__dict__, "env_set": frozenset({"SMTP_HOST", "SMTP_USERNAME"})})
    smtp = by_id(facts)["smtp"]
    assert smtp["status"] == "partial" and smtp["needs"] == ["SMTP_PASSWORD"]


def test_twilio_api_key_instead_of_account_sid_is_explained():
    facts = Facts(
        **{
            **NOTHING.__dict__,
            "twilio_sid_is_account": False,
            "env_set": frozenset({"TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"}),
        }
    )
    twilio = by_id(facts)["twilio"]
    assert twilio["status"] == "partial" and "AC" in twilio["label"]


@pytest.mark.parametrize(
    "patch,status,label",
    [
        ({"kill_switch": True, "live_sending": True}, "blocked", "KILL SWITCH"),
        ({"live_sending": True, "smtp_configured": False}, "blocked", "SMTP INCOMPLETE"),
        ({"live_sending": True, "smtp_configured": True, "sandbox": True}, "partial", "SANDBOX"),
        ({"live_sending": True, "smtp_configured": True, "sandbox": False}, "ready", "REAL E-MAIL"),
    ],
)
def test_sending_mode_follows_the_safety_switches(patch, status, label):
    item = by_id(Facts(**{**NOTHING.__dict__, **patch}))["sending_mode"]
    assert item["status"] == status and label in item["label"]


def test_ai_is_configured_only_when_a_provider_can_really_be_called_and_says_where_names_go():
    live = {
        "key_configured": True,
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "host": "api.groq.com",
        "active": True,
        "reason": None,
    }
    item = by_id(Facts(**{**NOTHING.__dict__, "ai": live}))["ai"]
    assert item["status"] == "unchecked" and item["test"] == "server" and item["needs"] == []
    assert ("sent to", "api.groq.com") in [tuple(f) for f in item["facts"]]
    assert "e-mail and phone never are" in item["hint"]  # what leaves the server is said
    no_key = {"key_configured": False, "provider": "groq", "active": False, "reason": "AI_API_KEY is not set"}
    item = by_id(Facts(**{**NOTHING.__dict__, "ai": no_key}))["ai"]
    assert (
        item["status"] == "partial"
        and item["needs"] == ["AI_PROVIDER", "AI_API_KEY"]
        and "AI_API_KEY" in item["summary"]
    )
    custom = {"key_configured": True, "provider": "custom", "active": False, "reason": "AI_BASE_URL is not set"}
    facts = Facts(**{**NOTHING.__dict__, "ai": custom, "env_set": frozenset({"AI_PROVIDER", "AI_API_KEY"})})
    assert by_id(facts)["ai"]["needs"] == ["AI_BASE_URL", "AI_MODEL"]  # a custom provider needs its address and model


@pytest.mark.parametrize(
    "kind,ok,status",
    [
        ("supabase_session_pooler", True, "ready"),
        ("supabase_direct", True, "partial"),
        ("render_postgres", True, "ready"),
        ("supabase_transaction_pooler", True, "ready"),
        ("local", False, "blocked"),
    ],
)
def test_database_status_and_advice_by_host_kind(kind, ok, status):
    item = by_id(Facts(**{**NOTHING.__dict__, "database_kind": kind, "database_ok": ok}))["database"]
    assert item["status"] == status
    assert (item["hint"] is not None) == (kind in {"supabase_direct", "render_postgres", "supabase_transaction_pooler"})


def test_public_url_must_be_a_real_address_in_production():
    def public(**kw):
        return by_id(Facts(**{**NOTHING.__dict__, **kw}))["public_url"]

    assert public(app_env="production", public_base_url=None)["status"] == "blocked"
    assert public(app_env="production", public_base_url="http://localhost:8000")["status"] == "blocked"
    assert public(app_env="production", public_base_url="http://api.example")["status"] == "partial"
    assert public(app_env="production", public_base_url="https://api.example")["status"] == "ready"
    assert public(app_env="development", public_base_url=None)["status"] == "ready"


def test_overpass_cooldown_is_shown_not_hidden():
    some = by_id(Facts(**{**NOTHING.__dict__, "overpass_cooling": ("a.example",)}))["osm"]
    assert some["status"] == "partial" and "1 OF 2" in some["label"]
    everything = by_id(Facts(**{**NOTHING.__dict__, "overpass_cooling": ("a.example", "b.example")}))["osm"]
    assert "ALL" in everything["label"]


def test_no_value_can_leak_only_names_and_derived_facts():
    secret = "s3cr3t-value-never-shown"
    facts = Facts(
        **{
            **NOTHING.__dict__,
            "smtp_configured": True,
            "smtp_host": "smtp.example",
            "env_set": frozenset({"SMTP_PASSWORD", "SMTP_HOST", "SMTP_USERNAME"}),
        }
    )
    assert secret not in repr(build(facts))
    assert "SMTP_PASSWORD" in repr(build(facts))  # the name is fine, it is what the user must set
