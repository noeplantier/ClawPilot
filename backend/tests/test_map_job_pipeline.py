"""Map search jobs end to end against a real database, with a FAKE Overpass: no network, ever.

Routes are called in process (the CI server runs with the flags off); the runner is awaited with an injected
fetcher, so each outcome of the source is reproducible: success, cache hit, timeout, 429, empty, invalid, crash.
"""

import asyncio
import json
import os
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
import requests
from fastapi import HTTPException
from sqlalchemy import text

os.environ.setdefault("DATABASE_URL", os.environ.get("DATABASE_URL", ""))

from models import MapParseIn, MapSearchIn  # noqa: E402
from repositories import map_job_repo  # noqa: E402
from routes import map_search, system  # noqa: E402
from services import map_job_runner, overpass_svc  # noqa: E402
from tasks import _bridge  # noqa: E402
from tasks._bridge import run_async  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "osm" / "overpass_lyon.json").read_text())
AREA = dict(south=45.75, west=4.82, north=45.77, east=4.85, category="restaurants")


@pytest.fixture(autouse=True)
def clean_cache():
    async def wipe(session):
        await session.execute(text("DELETE FROM source_cache"))

    run_async(wipe)


@pytest.fixture(autouse=True)
def flag_and_no_background(monkeypatch):
    monkeypatch.setenv("FEATURE_EXTERNAL_SOURCES", "true")
    scheduled: list = []
    monkeypatch.setattr(map_job_runner, "schedule_job", lambda job_id: scheduled.append(job_id))
    monkeypatch.setattr(map_search, "_limiter", map_search.AttemptLimiter(6, 60.0))
    monkeypatch.setattr(map_search, "_ingest_limiter", map_search.AttemptLimiter(12, 60.0))
    return scheduled


def _org():
    uid = uuid.uuid4().hex[:8]
    reg = requests.post(
        f"{API}/auth/register",
        json={
            "email": f"mj_{uid}@test.example",
            "password": uuid.uuid4().hex,
            "full_name": "Jobs",
            "organization_name": f"Jobs {uid}",
        },
    )
    assert reg.status_code == 200, reg.text
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    return requests.get(f"{API}/auth/me", headers=h).json()["user"]


def _create(user, **area):
    async def go(session):
        return await map_search.create_search(MapSearchIn(**{**AREA, **area}), user=user, session=session)

    return run_async(go)


def _run(job_id, fetcher):
    asyncio.run(map_job_runner.execute(uuid.UUID(job_id), session_factory=_bridge._SessionLocal, fetcher=fetcher))


def _status(user, job_id):
    async def go(session):
        return await map_search.search_status(job_id, user=user, session=session)

    return run_async(go)


def _places(user, job_id):
    async def go(session):
        return await map_search.search_places(job_id, user=user, session=session)

    return run_async(go)


def _failing(code, failures=("overpass-api.de: TimeoutError",)):
    def fetch(query):
        raise overpass_svc.Unavailable("down", code=code, failures=failures)

    return fetch


def test_creating_a_search_returns_at_once_with_a_queued_job_and_starts_the_runner(flag_and_no_background):
    user = _org()
    job = _create(user)
    assert job.status == "queued" and job.result_count == 0 and job.error is None
    assert flag_and_no_background == [uuid.UUID(job.id)]
    assert _status(user, job.id).status == "queued"


def test_a_successful_search_stages_the_places_and_they_survive_another_session():
    user = _org()
    seen = []
    job = _create(user)
    _run(job.id, lambda q: seen.append(q) or FIXTURE)
    done = _status(user, job.id)
    assert (
        done.status == "succeeded" and done.result_count == 3 and done.source == "overpass" and done.cache_hit is False
    )
    assert done.duration_ms is not None and done.finished_at is not None and done.error_code is None
    assert "nwr" in seen[0] and "[out:json]" in seen[0]
    out = _places(user, job.id)  # a fresh session, as after a refresh or on another device
    assert len(out.places) == 3 and "ODbL" in out.license_note
    names = {p.name: p for p in out.places}
    assert names["Boulangerie Martin"].email is None and names["Boulangerie Martin"].phone is None  # never invented
    assert all(p.source_url.startswith("https://www.openstreetmap.org/") for p in out.places)


def test_the_same_area_again_is_served_from_the_cache_without_asking_the_source():
    user = _org()
    first = _create(user)
    _run(first.id, lambda q: FIXTURE)
    second = _create(user, south=45.7512, west=4.8223, north=45.7688, east=4.8478)  # inside the same snapped area
    _run(second.id, lambda q: pytest.fail("the cache must answer"))
    done = _status(user, second.id)
    assert done.status == "succeeded" and done.cache_hit is True and done.source == "cache" and done.result_count == 3
    assert [p.external_id for p in _places(user, second.id).places] == [
        p.external_id for p in _places(user, first.id).places
    ]


def test_duplicates_in_one_answer_are_collapsed():
    user = _org()
    twin = {
        "elements": [
            {
                "type": "node",
                "id": 1,
                "lat": 45.7601,
                "lon": 4.8301,
                "tags": {"name": "Chez Dupont", "amenity": "restaurant"},
            },
            {
                "type": "way",
                "id": 2,
                "center": {"lat": 45.76011, "lon": 4.83011},
                "tags": {"name": "Chez  DUPONT", "amenity": "restaurant", "phone": "+33 4 78 11 22 33"},
            },
            {"type": "node", "id": 3, "lat": 45.7701, "lon": 4.8401, "tags": {"name": "Autre", "amenity": "cafe"}},
        ]
    }
    job = _create(user)
    _run(job.id, lambda q: twin)
    out = _places(user, job.id)
    assert sorted(p.name for p in out.places) == ["Autre", "Chez  DUPONT"]  # the entry with a published phone wins
    assert _status(user, job.id).result_count == 2


@pytest.mark.parametrize(
    "code",
    ["overpass_timeout", "overpass_busy", "overpass_unreachable", "overpass_bad_answer"],
)
def test_a_source_failure_is_a_stored_explained_state_with_a_browser_fallback(code):
    user = _org()
    job = _create(user)
    _run(job.id, _failing(code))
    failed = _status(user, job.id)
    assert failed.status == "failed" and failed.error_code == code and "overpass-api.de" in failed.error
    assert failed.fallback is not None and failed.fallback.query.startswith("[out:json]") and failed.fallback.endpoints
    with pytest.raises(HTTPException) as nothing:
        _places(user, job.id)
    assert nothing.value.status_code == 409


def test_an_area_too_large_for_one_answer_has_no_browser_fallback():
    user = _org()
    job = _create(user)
    _run(job.id, _failing("overpass_too_large", ()))
    failed = _status(user, job.id)
    assert failed.error_code == "overpass_too_large" and failed.fallback is None and "zoom in" in failed.error


def test_an_invalid_answer_and_an_unexpected_crash_both_end_the_job():
    user = _org()
    bad = _create(user)
    _run(bad.id, lambda q: {"unexpected": True})
    assert _status(user, bad.id).error_code == "overpass_bad_answer"

    def crash(query):
        raise RuntimeError("secret internal detail")

    boom = _create(user)
    _run(boom.id, crash)
    failed = _status(user, boom.id)
    assert failed.status == "failed" and failed.error_code == "internal_error" and "secret" not in failed.error


def test_an_empty_answer_is_a_success_with_zero_places():
    user = _org()
    job = _create(user)
    _run(job.id, lambda q: {"elements": []})
    done = _status(user, job.id)
    assert done.status == "succeeded" and done.result_count == 0 and _places(user, job.id).places == []


def test_a_job_lost_with_its_instance_is_reported_not_left_spinning():
    user = _org()
    job = _create(user)

    async def age(session):
        await session.execute(
            text("UPDATE map_search_jobs SET created_at = now() - interval '10 minutes' WHERE id = :i"), {"i": job.id}
        )

    run_async(age)
    lost = _status(user, job.id)
    assert lost.status == "failed" and lost.error_code == "job_lost"


def test_the_browser_can_complete_a_failed_job_explicitly_and_only_a_failed_one():
    user = _org()
    job = _create(user)

    def ingest(data):
        async def go(session):
            return await map_search.ingest_browser_answer(job.id, MapParseIn(data=data), user=user, session=session)

        return run_async(go)

    with pytest.raises(HTTPException) as early:
        ingest(FIXTURE)
    assert early.value.status_code == 409  # still queued
    _run(job.id, _failing("overpass_unreachable"))
    for bad in ({}, {"elements": "x"}, {"elements": [{}] * (map_search.MAX_PARSED_ELEMENTS + 1)}):
        with pytest.raises(HTTPException) as refused:
            ingest(bad)
        assert refused.value.status_code == 422
    done = ingest(FIXTURE)
    assert done.status == "succeeded" and done.source == "overpass_browser" and done.result_count == 3
    assert len(_places(user, job.id).places) == 3
    with pytest.raises(HTTPException) as twice:
        ingest(FIXTURE)
    assert twice.value.status_code == 409


def test_a_search_belongs_to_its_organisation():
    owner, other = _org(), _org()
    job = _create(owner)
    _run(job.id, lambda q: FIXTURE)
    for read in (_status, _places):
        with pytest.raises(HTTPException) as hidden:
            read(other, job.id)
        assert hidden.value.status_code == 404
    with pytest.raises(HTTPException):
        _status(other, "not-a-uuid")

    async def history(session, who):
        return await map_search.recent_searches(user=who, session=session)

    assert [j.id for j in run_async(lambda s: history(s, owner))] == [job.id]
    assert run_async(lambda s: history(s, other)) == []


def test_creation_is_closed_without_the_flag_validated_and_rate_limited(monkeypatch):
    user = _org()
    for bad in ({"south": 44.0}, {"category": "weapons"}, {"south": 45.9, "north": 45.8}):
        with pytest.raises(HTTPException) as refused:
            _create(user, **bad)
        assert refused.value.status_code == 422
    for _ in range(6):
        _create(user)
    with pytest.raises(HTTPException) as limited:
        _create(user)
    assert limited.value.status_code == 429
    monkeypatch.delenv("FEATURE_EXTERNAL_SOURCES")
    with pytest.raises(HTTPException) as closed:
        _create(_org())
    assert closed.value.status_code == 409


def test_old_jobs_and_their_staged_places_are_purged_for_the_organisation():
    user = _org()
    old = _create(user)
    _run(old.id, lambda q: FIXTURE)

    async def age(session):
        await session.execute(
            text("UPDATE map_search_jobs SET created_at = now() - interval '40 days' WHERE id = :i"), {"i": old.id}
        )

    run_async(age)
    _create(user)  # creating a search purges this organisation's expired ones

    async def count(session):
        jobs = (
            await session.execute(text("SELECT count(*) FROM map_search_jobs WHERE id = :i"), {"i": old.id})
        ).scalar_one()
        rows = (
            await session.execute(text("SELECT count(*) FROM map_search_results WHERE job_id = :i"), {"i": old.id})
        ).scalar_one()
        return jobs, rows

    assert run_async(count) == (0, 0)
    assert map_job_repo.RETENTION_DAYS == 30 and timedelta(days=map_job_repo.RETENTION_DAYS)


def test_every_table_of_the_public_schema_has_row_level_security():
    """Supabase serves the public schema through its Data API: a table without RLS would be open to the anon key."""

    async def tables(session):
        rows = await session.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT c.relrowsecurity"
            )
        )
        return [r[0] for r in rows.all()]

    assert run_async(tables) == []


def test_the_health_report_shows_the_database_the_migrations_and_the_jobs_without_any_secret():
    user = _org()
    job = _create(user)
    _run(job.id, lambda q: FIXTURE)

    async def go(session):
        return await system.health(user=user, session=session)

    report = run_async(go)
    assert report["database"]["ok"] is True and report["database"]["kind"] in ("local", "other", "render_postgres")
    assert report["migrations"]["ok"] is True and report["migrations"]["current"] == report["migrations"]["head"]
    assert report["cache"]["ok"] is True and report["map_jobs_24h"].get("succeeded", 0) >= 1
    assert report["workers"]["mode"] == "in_process" and report["flags"]["external_sources"] is True
    assert "password" not in json.dumps(report, default=str).lower()


def test_the_overpass_probe_reports_each_server_and_is_rate_limited(monkeypatch):
    probed = []
    monkeypatch.setattr(
        overpass_svc,
        "probe",
        lambda endpoint: probed.append(endpoint) or {"host": endpoint, "ok": False, "error": "x", "ms": 1},
    )
    monkeypatch.setattr(system, "_probe_limiter", system.AttemptLimiter(3, 60.0))
    user = _org()

    async def go():
        return await system.probe_overpass(user=user)

    out = asyncio.run(go())
    assert (
        out["ok"] is False
        and len(out["servers"]) == len(overpass_svc.ENDPOINTS)
        and probed == list(overpass_svc.ENDPOINTS)
    )
    for _ in range(2):
        asyncio.run(go())
    with pytest.raises(HTTPException) as limited:
        asyncio.run(go())
    assert limited.value.status_code == 429


def test_the_endpoints_need_a_login_over_http():
    assert requests.post(f"{API}/map/search", json=AREA).status_code in (401, 403)
    assert requests.get(f"{API}/map/search").status_code in (401, 403)
    assert requests.get(f"{API}/system/health").status_code in (401, 403)
