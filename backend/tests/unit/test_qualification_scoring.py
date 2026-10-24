from services.qualification_scoring import priority_for, score_qualification


def test_qualification_scores_are_deterministic_and_bounded():
    inputs = {
        "website_url": "https://company.example",
        "cache_data": {
            "emails": ["hello@company.example"],
            "phones": ["+33123456789"],
            "socials": ["https://linkedin.com/company/example", "https://instagram.com/example"],
            "technologies": ["wordpress", "shopify"],
            "has_form": True,
        },
        "company_name": "Company Ltd",
        "vertical": "retail",
        "city": "Paris",
        "country": "FR",
        "email": None,
        "phone": None,
        "title": "Owner",
    }
    first = score_qualification(**inputs)
    assert first == score_qualification(**inputs)
    assert first.website_quality == 100
    assert first.digital_maturity == 95
    assert first.fit_score == 99
    assert first.priority == "high"


def test_priority_thresholds_and_missing_signals_are_explicit():
    assert [priority_for(score) for score in (0, 49, 50, 74, 75, 100)] == [
        "low",
        "low",
        "medium",
        "medium",
        "high",
        "high",
    ]
    score = score_qualification(
        website_url="http://minimal.example",
        cache_data={},
        company_name=None,
        vertical=None,
        city=None,
        country=None,
        email=None,
        phone=None,
        title=None,
    )
    assert score.website_quality == 30
    assert score.digital_maturity == 20
    assert score.fit_score == 13
    assert score.priority == "low"


def test_unknown_cache_values_do_not_invent_contact_or_stack_signals():
    score = score_qualification(
        website_url="https://minimal.example",
        cache_data={"emails": "not-a-list", "phones": [None], "socials": [], "technologies": []},
        company_name="Minimal",
        vertical=None,
        city=None,
        country=None,
        email=None,
        phone=None,
        title=None,
    )
    assert score.website_quality == 40
    assert score.digital_maturity == 30
    assert score.fit_score == 28


def test_malformed_stored_website_does_not_fail_the_batch_scorer():
    score = score_qualification(
        website_url="http://[malformed",
        cache_data={},
        company_name="Malformed site",
        vertical=None,
        city=None,
        country=None,
        email=None,
        phone=None,
        title=None,
    )
    assert score.website_quality == 30
    assert score.digital_maturity == 20


def test_celery_registers_the_daily_job_on_the_automation_queue():
    from celery_app import celery_app

    schedule = celery_app.conf.beat_schedule["score-enriched-leads"]
    assert schedule["task"] == "tasks.qualification_tasks.score_enriched_leads"
    assert schedule["options"]["queue"] == "automation"
    assert "tasks.qualification_tasks" in celery_app.conf.include
