# PR 2 — deterministic lead qualification

The daily Celery job `tasks.qualification_tasks.score_enriched_leads` reads only active leads joined to a completed `PublicPageCache` row. It performs no network request, AI call, or outreach action. It processes at most 200 rows per database transaction and only revisits a row when it has not been scored or its lead/cache data is newer than `qualification_scored_at`.

## Scores

- `website_quality` (0–100): cached successful website (30), HTTPS (10), known email (20), known phone (15), contact form (15), and at least one social profile (10).
- `digital_maturity` (0–100): website (20), HTTPS (10), contact form (25), up to two observed platform signals (15 each), and up to three observed social profiles (5 each).
- `fit_score` (0–100): 50% CRM profile completeness, 30% website quality, and 20% digital maturity. This is a transparent qualification proxy, not an ICP or conversion prediction.
- `priority`: high at 75+, medium at 50–74, low below 50.

Missing enrichment remains NULL; the job does not infer absent facts. Re-running the job with unchanged source rows produces no score updates. The fields are separate from `Lead.score`, which retains its existing behavior.

## Schema and verification

Alembic revision `368034440904` adds nullable scores, the qualification timestamp, range/consistency checks, an account/priority/score partial index, and partial website indexes for the batch join. Existing leads are not backfilled by migration. The scheduled job scores eligible rows after migration. Downgrade removes the new indexes, checks, and columns.

Run the pure scoring tests with `PYTHONPATH=. ./.venv/bin/pytest -q tests/unit/test_qualification_scoring.py`; the PostgreSQL-backed job test is `PYTHONPATH=. ./.venv/bin/pytest -q tests/test_qualification_job.py`. The standard backend CI runs migrations and the full suite. No new environment variable or dependency is required.
