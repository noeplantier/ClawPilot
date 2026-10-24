# PR 1 — map discovery, CRM conversion and free enrichment

## Behavior

- Authenticated users can search a bounding box up to 0.12 degrees in each dimension and choose a supported OSM category.
- A normalized bounding box, category and query version share one discovery job for 12 hours. Active and completed searches are reused. Results are upserted by the account-scoped OSM element identifier.
- Overpass runs in the Celery `automation` queue with three public endpoints and bounded retries. Search responses are persisted and can be polled through the API.
- A selected map result creates one company and lead, plus an audit event. A primary contact is created only when OSM provides a named contact person; the business name is never passed off as a person's name. Repeated clicks return the existing lead.
- Enrichment is an explicit queue action. It checks the website host resolves to public IPs, requests only the homepage and four common contact/about/legal paths, limits each response, extracts public contact/social/technology signals and caches the result for 30 days by URL. There is no AI call.
- Overpass responses are capped at 5 MB. Website requests are limited to five pages of at most 1 MB each, with short timeouts, no redirects, and DNS checks that reject non-public addresses.
- This feature does not create or schedule any email or WhatsApp send.

## Migration and Render

Apply Alembic revision `20261024_01` after the current `a8c4d5e6f7b9` head before deploying the backend. It creates company, discovery, enrichment and URL cache tables plus their account/status/deduplication indexes, links leads to companies with a nullable FK, and enables row-level security on each new table with no Supabase Data API policies.

No new secret or environment variable is required. The Render Celery worker must consume the existing `automation` queue (the repository's `docker-compose.yml` worker already does). API and worker continue to use the existing `DATABASE_URL` and Celery broker configuration; do not copy their values into a deployment log or PR.

## Verification

In staging, apply the migration, verify a small bounding-box job reaches `completed`, click one result twice and confirm one company/lead exists, queue enrichment twice and confirm one active job exists, and inspect URL cache timestamps. Confirm that no contact is created without a source-provided person's name and no send record is created. Check that OSM attribution is displayed.

Local checks for this revision: backend isort, Black and Flake8 pass; `PYTHONPATH=. ./.venv/bin/pytest -q tests/test_prospecting.py` passes (4 tests), and the unit suite passes (499 tests). Alembic has one head and offline SQL generation passes. The database-backed migration/check and integration suite run in CI with PostgreSQL and Redis; no MongoDB client or active MongoDB test is present in this repository. Frontend lint passes with 10 existing warnings, Jest passes 262 tests, and build passes. Playwright is not configured for this flow.

## Risks and rollback

- Overpass is a public service and may rate-limit or be unavailable. The job reports a bounded failure code; retry only through the normal search flow after the failure, and keep the requested search area small.
- Public websites can be slow or malformed. The worker fetches at most five pages, caps each response at 1 MB, uses short timeouts, rejects non-public DNS results, and does not follow redirects. The cache retains successful results for 30 days and failures for 6 hours.
- The migration adds tables, indexes and a nullable `leads.company_id` foreign key. Validate duration and schema drift in staging against a production-sized copy before rollout. There is no data backfill or seed step.
- Enrichment stores publicly published business contact details. It runs only after a user requests it; apply the existing account deletion and data-retention processes to these rows.

For an application rollback, stop or drain the `automation` worker queue, roll back the Render API/worker and Netlify frontend to their previous releases, and leave the additive schema in place while checking queued work. The migration downgrade is reversible only before this feature creates data; after rollout, its tables contain user-requested discovery/enrichment data. Do not run a production downgrade automatically. If schema removal is later required, back up the database, drain workers, verify data-retention approval, and run the reviewed downgrade in a separately approved maintenance window.
