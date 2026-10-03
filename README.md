# Plantiers - OutreachOS

> Formerly *ClawPilot*. Technical identifiers that would break a running deployment (database and Render service names, `clawpilot` in `docker-compose.yml` and CI) keep the old spelling until a planned infrastructure migration; see `backend/tests/unit/test_branding.py`.

B2B lead-generation and multi-channel outreach platform: lead ingestion, scoring,
email/WhatsApp sequences, CRM pipeline, analytics, and automation — built to run
autonomously with human oversight.

## Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0 (async) + Alembic, PostgreSQL
- **Frontend**: React 19, React Router, Tailwind, Radix UI
- **Jobs**: Celery + Redis — three queues (`sends`, `automation`, `webhooks`), per-channel
  rate limits, timezone-aware send windows, and beat-scheduled automation (rescoring,
  stopping unqualified sequences, reactivating dormant leads)
- **Email / WhatsApp**: SendGrid, Twilio (WhatsApp Business Platform BSP)
- **Contributing**: see [`CLAUDE.md`](CLAUDE.md) for architecture rules, compliance
  rules, lint/test commands and the branch/commit conventions

## Repository layout

```
backend/
  server.py            FastAPI entry point
  routes/               HTTP endpoints (one file per domain)
  repositories/         The only layer that touches SQLAlchemy directly
  db/
    models/             SQLAlchemy ORM models (19+ tables)
    base.py, session.py Declarative base, async engine/session
  alembic/              Migrations
  services/              SendGrid/Twilio/AI wrappers, scoring, templating, scheduler
  celery_app.py          Celery app + beat schedule
  tasks/                 Celery tasks (sends, automation, webhooks)
  scripts/
    seed_demo.py           local demo account + sample data (idempotent, dev only)
    gen_schema_doc.py      regenerates docs/schema.md from the ORM models
  tests/                 Backend integration test suite (pytest)
frontend/
  src/                   React app (pages, components, contexts, lib)
render.yaml             Render Blueprint (API, worker, beat, Postgres, Redis)
docker-compose.yml       Postgres, Redis, Mailpit, backend, worker, beat
.github/workflows/ci.yml Lint, migration check, tests, build, deploy
```

## Local development

### Option A — Docker Compose

```bash
cp backend/.env.example backend/.env      # fill in secrets as needed
docker compose up --build
cd backend && alembic upgrade head        # first run only
docker compose exec backend python -m scripts.seed_demo   # optional demo account
```

Backend: http://localhost:8000/api/health · Mailpit (test emails): http://localhost:8025

### Option B — native (Postgres/Redis installed locally)

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt           # runtime + lint + tests (CI uses the same file)
cp .env.example .env                      # set DATABASE_URL, JWT_SECRET, ...
alembic upgrade head
python -m scripts.seed_demo                # optional demo account
uvicorn server:app --reload

# Background jobs (separate shells) — needed for scheduled sends and automation
celery -A celery_app worker -Q sends,automation,webhooks -l info
celery -A celery_app beat -l info

# Frontend (separate shell)
cd frontend
cp .env.example .env
npm install --legacy-peer-deps            # pre-existing date-fns/react-day-picker peer conflict
npm start
```

## Dependencies

| File | Role |
|---|---|
| `backend/requirements.in` | The ~20 **direct** runtime dependencies, one comment each saying why. The only file to edit by hand. |
| `backend/requirements.txt` | Production lock (61 packages): what the Docker image installs. Generated and tested, never edited by hand. |
| `backend/requirements-dev.in` / `requirements-dev.txt` | Adds pytest, requests, httpx, black, isort, flake8, mypy. Used by CI and local development, never in the image. |

Rule: a package is added only if code imports it or a runtime needs it, with the reason in the `.in` comment. To change one,
edit the `.in` file, then regenerate the locks in clean virtualenvs and run the whole suite on them:

```bash
python3 -m venv /tmp/rt  && /tmp/rt/bin/pip  install -r requirements.in     && /tmp/rt/bin/pip  freeze --exclude pip --exclude setuptools --exclude wheel
python3 -m venv /tmp/dev && /tmp/dev/bin/pip install -r requirements-dev.in && /tmp/dev/bin/pip freeze --exclude pip --exclude setuptools --exclude wheel
# keep the 2-line header of each lock file, replace the rest, then: alembic upgrade head && alembic check && pytest tests/
```

The previous `pip freeze` of ~130 packages (LLM SDKs, `boto3`, `stripe`, `pandas`, `numpy`, `huggingface_hub`, `litellm`, `openai`,
`google-*`, `jq`, `s5cmd`, …) was not imported by any code and was removed. `emergentintegrations` (AI composer) is optional and
installed from a private index; without it the composer returns a template (see Settings).

## Environment variables

See [`backend/.env.example`](backend/.env.example) and
[`frontend/.env.example`](frontend/.env.example) for the full list. Nothing is
required to boot in a degraded/mock mode except `DATABASE_URL` and `JWT_SECRET` —
SendGrid/Twilio/AI all fall back to graceful mocks when unconfigured.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL (`postgres://` / `postgresql://` are auto-converted to the asyncpg driver) |
| `JWT_SECRET` | Signs access tokens — generate with `openssl rand -hex 32` |
| `APP_ENV` | `production` makes `scripts/seed_demo.py` refuse to run |
| `CORS_ORIGINS` | Comma-separated allowed origins (default `http://localhost:3000`; never `*`) |
| `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `REDIS_URL` | Redis for Celery |
| `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL` | Email (mock when unset) |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM` | WhatsApp (mock when unset) |
| `TWILIO_WEBHOOK_URL` | Exact public URL Twilio calls (e.g. `https://api.example.com/api/webhooks/twilio`); used to verify `X-Twilio-Signature` |
| `SENDGRID_WEBHOOK_PUBLIC_KEY` | Verification key for `X-Twilio-Email-Event-Webhook-Signature` on `POST /api/webhooks/sendgrid` |
| `OUTREACH_SENDER_NAME`, `_COMPANY`, `_ADDRESS`, `_EMAIL` | Sender identity printed in drafts; all four required, no default |
| `PUBLIC_BASE_URL` | Public API URL (https in production), used in unsubscribe links |
| `FEATURE_PROSPECT_IMPORT` | `true` lets owners/admins import a prospect list (CSV/JSON); off by default |
| `FEATURE_LIVE_SENDING`, `FEATURE_EXTERNAL_SOURCES` | Dangerous capabilities, off unless `true`. Live sending = real e-mail over SMTP (below); no network source exists yet |
| `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_SECURITY`, `SMTP_PORT` | The real e-mail channel. The first three are required; `SMTP_SECURITY` is `starttls` (587, default) or `ssl` (465); TLS is verified and mandatory |
| `IMAP_HOST`, `IMAP_USERNAME`, `IMAP_PASSWORD`, `IMAP_PORT`, `IMAP_FOLDER` | Reads replies, hard bounces and STOP from the sending mailbox (TLS only, port 993, folder `INBOX` by default). The first three are required; without them nothing is read. Run by beat every 5 minutes where a worker exists, or by `POST /api/outbound/sync-inbox` |
| `OUTREACH_SANDBOX`, `OUTREACH_LIVE_ALLOWLIST` | While live sending is on, only the allowlisted addresses/`@domains` receive mail. The sandbox is on unless set to `false`; an empty allowlist allows nobody |
| `SEND_KILL_SWITCH` | `true` halts every send immediately (dispatch, SMTP test, SendGrid, Twilio) |
| `EMERGENT_LLM_KEY` | AI composer (mock when unset) |
| `REACT_APP_BACKEND_URL` (frontend) | API base URL |

## OutreachOS: local prospect journey (dry-run, no network)

Fixture directory → normalisation → deduplication → signals → explainable score → human review → e-mail draft.
Nothing is sent by default: `FEATURE_LIVE_SENDING` is off and the channel adapter is a dry-run one that never opens a socket
(real SMTP sending is opt-in, see below). Design: [`docs/architecture.md`](docs/architecture.md);
rules: [`docs/compliance.md`](docs/compliance.md), [`docs/threat-model.md`](docs/threat-model.md),
[`docs/cost-control.md`](docs/cost-control.md), [`docs/deployment.md`](docs/deployment.md).

```bash
cd backend
export OUTREACH_SENDER_NAME="Your Name" OUTREACH_SENDER_COMPANY="Your Company" \
       OUTREACH_SENDER_ADDRESS="1 rue Fictive, 69000 Lyon" OUTREACH_SENDER_EMAIL=you@example.com   # drafts need these
alembic upgrade head && python -m scripts.seed_demo && uvicorn server:app --port 8000 &
TOKEN=$(curl -s localhost:8000/api/auth/login -H 'content-type: application/json' \
  -d '{"email":"demo@outreachos.example","password":"Demo12345!"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
H="Authorization: Bearer $TOKEN"
curl -s -X POST localhost:8000/api/prospects/discovery/run -H "$H" -H 'content-type: application/json' -d '{}'   # 9 listings → 7 prospects
curl -s localhost:8000/api/prospects -H "$H"                                    # ranked by score
curl -s localhost:8000/api/prospects/<id> -H "$H"                               # sources, signals + evidence, score breakdown
curl -s -X POST localhost:8000/api/prospects/<id>/review -H "$H" -H 'content-type: application/json' -d '{"decision":"approve"}'
curl -s -X POST localhost:8000/api/prospects/<id>/drafts -H "$H"                # dry-run draft (idempotent)
```

Endpoints (`/api/prospects`): `discovery/run`, list, detail, `review`, `rescore`, `drafts`, `drafts/{id}/review`, `events`
(audit history), `erase`, `suppressions`, `score-config`, `settings`; public `GET|POST /api/unsubscribe/{token}`.
The score is 0–100; a signal is `detected`, `not_detected` or `unknown`, and only `detected` adds points — a missing
observation never counts against a prospect. See the screens below.

### Screens

Sign in, then open **Prospects**, **Review queue** or **Sending** in the sidebar (`frontend/`, React in JavaScript).

| Screen | Route | What it shows |
|---|---|---|
| Prospects | `/app/prospects` | Real list ranked by score, filters (review status, minimum score), per-status counts, "Run discovery (dry-run)" |
| Prospect detail | `/app/prospects/:id` | Review decision, **score justification** (per-signal state, weight, points, evidence, config version), signals, drafts (prepare, approve, dispatch), **provenance** of every source, **history** (decisions, drafts, message events), erasure |
| Review queue | `/app/prospects/review` | One pending prospect at a time, best score first, with its evidence: approve, reject or skip |
| Sending | `/app/sending` | Mode and kill-switch state, counts and next allowed time, limits form, pause/resume, dispatched messages with simulate-reply/bounce |

Nothing on these screens is a placeholder: every number comes from the API, and an empty list says so and what to do
("not scored" is shown instead of 0 when a prospect was never scored). `unknown` signals are shown as unknown and never count
against a prospect. Deciding, dispatching and changing limits are disabled for non-owner/admin roles (the API enforces it too).

```bash
cd frontend && cp .env.example .env && npm start          # REACT_APP_BACKEND_URL=http://localhost:8000
npm run lint && npm test -- --watchAll=false && npm run build
```

### Controlled e-mail dispatch (dry-run)

An approved draft can be *dispatched* through a `ChannelAdapter`: the dry-run adapter by default (the "send" is recorded and
nothing leaves the process), the SMTP adapter when `FEATURE_LIVE_SENDING=true`. Order of checks: kill switch → account pause → draft and prospect approved → not suppressed,
not opted out → draft carries sender identity, data origin and unsubscribe link → send limits → adapter. A draft produces at
most one message (idempotent). Every refusal is audited, even though the call returns 4xx.

```bash
curl -s -X POST localhost:8000/api/outbound/dispatch -H "$H" -H 'content-type: application/json' -d '{"draft_id":"<id>"}'
curl -s localhost:8000/api/outbound/status -H "$H"                       # counts, next allowed time, what blocks
curl -s -X PUT localhost:8000/api/outbound/limits -H "$H" -H 'content-type: application/json' \
  -d '{"max_per_day":20,"max_per_hour":10,"min_delay_seconds":60}'      # defaults are 20 / 100 / 60
curl -s -X PUT localhost:8000/api/outbound/limits -H "$H" -H 'content-type: application/json' -d '{"sending_paused":true}'
curl -s -X POST localhost:8000/api/outbound/<message_id>/simulate -H "$H" -H 'content-type: application/json' \
  -d '{"event":"replied","text":"STOP"}'                                # or {"event":"bounced"}
```

- **Limits** (per organisation, per day in the organisation's timezone): daily cap, rolling hourly cap, minimum delay.
  Over a limit ⇒ `429` with `retry_at` and `Retry-After`.
- **Pause** (`sending_paused`) ⇒ `423`. **`SEND_KILL_SWITCH=true`** (environment, applies to everyone, no database needed)
  refuses dry-run dispatch **and** the existing SendGrid and Twilio senders.
- **One gate for every path.** The same pause and limits apply to the single send (`POST /api/messages/email|whatsapp`),
  the batch sends, a campaign step (`run-step`), `launch` and the Celery send tasks (`services/send_gate.py`). All paths
  count toward the same daily/hourly caps, so changing path never resets them, and a per-organisation lock stops parallel
  requests from overshooting. A single send over a limit answers `423`/`429` like the dispatch; a batch or campaign step
  stops at the first refusal and reports `dispatched`, `not_attempted` and `blocked` (nothing is queued behind your back);
  a Celery task is rescheduled for when the limit frees up. `launch` really sends the first step (it used to display
  invented sent/opened/replied/converted figures): the counters only ever reflect real attempts.
- **Bounce** (simulated) suppresses the address. **Reply**: a STOP-style reply opts the prospect out immediately; any
  other reply is only recorded. Real providers will drive the same code from their webhooks.
- Every message carries `List-Unsubscribe` / `List-Unsubscribe-Post` (RFC 8058) next to the link in the body.
- `FEATURE_LIVE_SENDING=true` **without complete SMTP settings is refused** (`501`) rather than silently falling back.

Endpoints (`/api/outbound`): `dispatch`, list, detail (with events), `simulate` (dry-run only), `limits` (GET/PUT), `status`,
`test-send`.

### Tests

`cd backend && pytest tests/` (server running, see `.github/workflows/ci.yml`); `cd frontend && npm test -- --watchAll=false`;
**E2E** (Playwright, real API and PostgreSQL, dry-run, no network): start the API, `REACT_APP_BACKEND_URL=http://localhost:8000 npm run build`,
then `npm run e2e` in `frontend/` (set `PW_CHROMIUM` to a Chromium binary if the browser is not installed with `npx playwright install chromium`).
Login is rate limited (10 failures per address per 15 min), see `docs/deployment.md`.

### Dashboard

`GET /api/dashboard/overview` (any member) feeds the home page: KPIs (prospects, average score, sent today, replies, bounces,
unsubscribed), a 14-day sends/replies series (UTC), latest prospects and detected signals, campaign health, limits & compliance
(quota left, kill switch, pause, sandbox allowlist, SMTP) and the latest replies. Every figure is computed from stored rows; `null`
means "nothing known yet" and is shown as an em dash, never as 0 (an average score, or a rate with nothing sent). The page refreshes
every 30 s while visible; an owner/admin can pause or resume sending from it. Replies and bounces only exist for dry-run
(simulated) messages or what you record by hand: real mailbox/webhook tracking is not wired, and the Inbox says so.

### Import your own prospect list (opt-in)

`FEATURE_PROSPECT_IMPORT=true`, then *Prospects → Import a list* (or `POST /api/prospect-imports`, owner/admin). CSV (`,` or `;`) or JSON,
up to 1000 rows / 2 MB; columns `name` (required), `email`, `phone`, `website`, `address`, `postcode`, `city`, `category`,
`description`, `hours`, `last_updated`, `external_id`, `source_url` (French aliases accepted). Two steps: **preview** (default, writes
nothing: valid rows, errors by row number, duplicates merged, addresses on the do-not-contact list, what would be created/updated)
then the import, which needs `attestation: true`, a free-text **origin** and a **legal basis**, recorded with the file's SHA-256 in
`prospect_import_batches` (the rows themselves are not kept in the batch; each prospect's provenance is its `prospect_sources` row, whose
`source_name` is `import:<batch>`). Imported prospects are deduplicated against existing ones, skip suppressed identities, and enter as
`pending` human review. **An empty cell is UNKNOWN, never a finding** (no "no website" claim from a blank column), and nothing is
fetched from the web, so site signals stay UNKNOWN until a sanctioned enrichment exists. Nothing is sent by importing.

### Real e-mail over SMTP (opt-in)

Set `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `OUTREACH_SENDER_EMAIL` (e.g. `founder@plantiers.com`) and
`FEATURE_LIVE_SENDING=true`. Real sending then stays in a **sandbox**: only `OUTREACH_LIVE_ALLOWLIST` can receive anything
until `OUTREACH_SANDBOX=false` is set on purpose. Check the connection first with
`POST /api/outbound/test-send {"to": "founder@plantiers.com"}` (sender's own address or allowlist only; owner/admin).
The message row is written as `sending` and committed **before** the SMTP call (at most once: a message left in `sending` has an
unknown outcome and is never resent by the system); a clean failure is `failed` and the draft can be dispatched again.
Full procedure (SPF/DKIM/DMARC, kill-switch drill, known limits): [`docs/go-live-email.md`](docs/go-live-email.md).
Not covered yet: a real prospect source (only the fictional directory exists), bounce/reply tracking over SMTP, and the
legacy Messages/campaign paths (SendGrid or mock, no unsubscribe footer).
Go-live requirements are in [`docs/deployment.md`](docs/deployment.md).

Tests: `pytest tests/unit` runs offline with no server or database; `pytest tests/test_outreach_prospects.py` is the end-to-end
journey against a running server (needs the `OUTREACH_SENDER_*` variables above on the server).

## Webhook security

`POST /api/webhooks/twilio` verifies `X-Twilio-Signature` with `TWILIO_AUTH_TOKEN` and returns
403 otherwise, so nobody can forge replies or STOP opt-outs. It fails closed: with `APP_ENV=production`
and no token, every call is rejected. Without a token outside production (local mock mode) calls are
accepted unsigned, with a warning in the log. Set `TWILIO_WEBHOOK_URL` to the exact URL configured in
Twilio — behind a proxy the URL the app sees differs from the one Twilio signed.
`POST /api/webhooks/sendgrid` follows the same rule with SendGrid's ECDSA signature: set
`SENDGRID_WEBHOOK_PUBLIC_KEY` (Mail Settings → Event Webhook → Signature Verification). Until you do, it rejects
every call in production — no SendGrid account is needed to run the app, only to receive its events.

## Settings page

Settings shows the live configuration of the server (`GET /api/settings/integrations`): the AI composer is "live" only if
`EMERGENT_LLM_KEY` is set **and** the optional `emergentintegrations` package is installed (otherwise it returns a fixed
template, and the page says why); SendGrid, Twilio, prospect outreach (dry-run / live / kill switch / sender identity) and
webhook signatures are each computed, and a banner lists the environment variables still missing. No status is hard-coded,
and no secret is ever returned.

## Demo account

New accounts start **empty**. For local development, `python -m scripts.seed_demo`
(from `backend/`) creates `demo@outreachos.example` / `Demo12345!` with sample leads and campaigns.
It is idempotent and refuses to run with `APP_ENV=production`. The demo login goes through the
real `/api/auth/login` — there is no client-side bypass.

## Database schema

[`docs/schema.md`](docs/schema.md) is generated from the ORM models:
`cd backend && python -m scripts.gen_schema_doc` (`--check` fails if it is stale).

## Tests

```bash
cd backend
# start the API first (uvicorn or docker compose), then:
REACT_APP_BACKEND_URL=http://localhost:8000 pytest tests/ -v
```

The suite is HTTP-integration style — it hits a running server, it does not use
`TestClient`/mocks. `.github/workflows/ci.yml` starts the server itself before
running it.

## Database migrations

```bash
cd backend
alembic revision --autogenerate -m "description"   # after changing db/models/
alembic upgrade head
alembic check                                       # verify no model/migration drift
```

## Deployment

- **Frontend**: Netlify, configured by [`netlify.toml`](netlify.toml) at the repo root (base `frontend`, publish
  `build`). Leave the UI "Base directory" empty or set it to `frontend`, and set `REACT_APP_BACKEND_URL` in the
  site's environment variables.
- **Backend**: Docker image via `backend/Dockerfile`, deployed to Render. CI
  triggers a deploy on every push to `main` via `RENDER_DEPLOY_HOOK_URL` (repo
  secret) once tests and the frontend build pass.
- [`render.yaml`](render.yaml) is a Render Blueprint: API, Celery worker, Celery beat,
  PostgreSQL and Redis. `alembic upgrade head` runs as the API's pre-deploy command.
  Secrets (`SENDGRID_*`, `TWILIO_*`, `CORS_ORIGINS`) are `sync: false` — set them in the dashboard.

## Status & roadmap

Implemented: Postgres schema, consent tracking and enforcement, weighted lead scoring,
Celery-based throttled sends with send windows, CRM (notes, tasks, tags, kanban),
real analytics. See [`memory/PRD.md`](memory/PRD.md) for the detailed history.

Next: automatic prospect sourcing for local businesses, digital-gap scoring, per-vertical
email sequences with reply detection, and an inbox view — broken down into short,
independent work sessions in [`docs/cloud-sessions.md`](docs/cloud-sessions.md).
