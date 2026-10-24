# PR 1 — map discovery, CRM conversion and free enrichment

## Behavior

- Authenticated users can search a bounding box up to 0.12 degrees in each dimension and choose a supported OSM category.
- A normalized bounding box, category and query version share one discovery job for 12 hours. Active and completed searches are reused. Results are upserted by the account-scoped OSM element identifier.
- Overpass runs in the Celery `automation` queue with three public endpoints and bounded retries. Search responses are persisted and can be polled through the API.
- A selected map result creates one company, lead and primary contact, plus an audit event. Repeated clicks return the existing lead.
- Enrichment is an explicit queue action. It checks the website host resolves to public IPs, requests only the homepage and four common contact/about/legal paths, limits each response, extracts public contact/social/technology signals and caches the result for 30 days by URL. There is no AI call.
- This feature does not create or schedule any email or WhatsApp send.

## Migration and Render

Apply Alembic revision `20261024_01` before deploying the backend. It creates company, discovery, enrichment and URL cache tables plus their account/status/deduplication indexes, and links existing-compatible leads to companies with a nullable FK.

No new secret or environment variable is required. The Render Celery worker must consume the existing `automation` queue (the repository's `docker-compose.yml` worker already does). API and worker continue to use the existing `DATABASE_URL` and Celery broker configuration; do not copy their values into a deployment log or PR.

## Verification

Run backend tests, frontend lint/build, and the existing CI workflow. In a staging deployment, apply the migration, verify a small bounding-box job reaches `completed`, click a result twice and confirm only one company/lead/contact exists, queue enrichment twice and confirm only one active job exists, and inspect the URL cache timestamps. Confirm that no send record was created. OSM attribution is displayed in the UI.
