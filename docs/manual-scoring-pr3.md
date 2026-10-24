# PR 3: manual scoring, job tracking and operational health

## Objective and changes

This change lets an authenticated account queue deterministic scoring for selected, enriched leads and follow progress in the CRM. It adds account-scoped `job_runs`, a Celery task on the `automation` queue, job status and system health routes, lead selection and score presentation, and operational documentation. It does not call Groq or send email, WhatsApp, SMS, or calls.

## Database migration

Alembic revision `6b81835a1403` adds `job_runs`, its account/status/creation-time index, constraints, and row-level security. It has no seed data or backfill. The table is additive. The downgrade drops only the new table and index. The application currently connects through its server-side database owner and all job reads are explicitly filtered by authenticated `account_id`; the Supabase Data API remains closed to public roles, in line with existing schema policy. No Realtime publication is added.

Apply the migration through the normal deployment migration step after review. Never run a production migration manually. To roll back, roll back the application first, then use the normal deployment rollback procedure to the previous revision; only use Alembic downgrade in a reviewed maintenance window if the new table must be removed and contains no records that need retention.

## API

- `POST /api/leads/score` accepts a `lead_ids` array containing 1–200 unique UUIDs. It verifies ownership before creating a persisted job and responds `202` with `job_id`, `queued` status, and `lead_count`.
- `GET /api/jobs/{job_id}` returns progress only when the authenticated account owns the job; otherwise it returns `404`.
- `GET /api/system/health` returns a timestamped snapshot, account-scoped recent job history and usage, migration state, database/cache state, Celery worker/Beat/queue state, and integration configuration state. It never returns credentials.
- `POST /api/system/health/overpass` performs a rate-limited, explicit reachability check against the configured public Overpass endpoints. No SMTP, IMAP, or Groq connectivity probe is run.

The worker processes selections in batches and persists progress. Enrichment must already be present in the existing cache. Unenriched or deleted leads are reported as failed items with a sanitized explanation and are not scored. Re-delivery of a terminal job is a no-op. A retry after a transient database error resumes through the same persisted job.

## Frontend and live updates

The Leads page queues selected leads, polls the authenticated job endpoint while it is active, shows persisted progress, and refreshes lead data when complete. Missing enrichment is shown explicitly. Scores and priority are displayed only when present in the database.

Polling is used instead of Supabase Realtime: the application authenticates with its own account JWT, while the Supabase Data API has no public grants/policies for these tables. Adding browser Realtime without a safe mapping from that JWT to database RLS would risk cross-account exposure. No service-role key or Realtime publication is used. The System Health page refreshes its authenticated snapshot every 15 seconds.

SMTP/IMAP and Groq indicators report only whether configuration is present; they do not claim connectivity. Overpass remains `not_checked` until an operator explicitly runs its rate-limited probe. Quota usage is read from persisted usage records; numeric plan limits are not configured by this change and are reported as such.

## Tests

CI runs backend style checks, unit/integration tests with PostgreSQL and Redis services, Alembic checks, frontend lint/tests/build, and the Playwright journey with a real API and Celery worker. Manual scoring integration tests create isolated test accounts and leads, verify authorization, limits, job persistence, enrichment requirements, idempotence, and RLS. No provider, transport, or worker behavior is mocked in the end-to-end journey.

## Risks

- The migration must finish before the new API version serves requests.
- A missing or unhealthy automation worker leaves jobs queued; the health page reports worker, Beat heartbeat, and queue depth.
- The integration statuses for SMTP, IMAP, and Groq are configuration indicators only. They do not test provider reachability.
- No numeric quota thresholds are configured here.
- Scoring covers only cached, completed enrichment and does not initiate enrichment.

## Production verification

After merge and the normal deployment migration, confirm the deployed revision is `6b81835a1403`, `/api/system/health` reports the expected migration head and live worker/Beat/automation queue, and no secrets appear in the report. In the app, select one already enriched lead, queue scoring, confirm progress reaches a terminal status, and verify the stored score and priority. Repeat the same job delivery through the worker's normal retry/redelivery path and confirm score values/timestamp stay stable. Select an unenriched lead and confirm the job reports the required-enrichment result without creating a score. Do not use email, WhatsApp, phone, SMTP/IMAP, or Groq test actions for this verification.

## Rollback

If API or worker errors occur, stop using manual scoring and roll back the application deployment to the previous release. Keep the additive `job_runs` table in place unless removal is specifically required. If removal is required, preserve any operational records first, then perform the reviewed Alembic downgrade through the normal controlled deployment process. Do not manually alter production schema.
