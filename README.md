# ClawPilot

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
pip install -r requirements.txt
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
| `EMERGENT_LLM_KEY` | AI composer (mock when unset) |
| `REACT_APP_BACKEND_URL` (frontend) | API base URL |

## OutreachOS: local prospect journey (dry-run, no network)

Fixture directory → normalisation → deduplication → signals → explainable score → human review → e-mail draft.
Nothing is sent: `FEATURE_LIVE_SENDING` is off and no sending adapter exists yet. Design: [`docs/architecture.md`](docs/architecture.md);
rules: [`docs/compliance.md`](docs/compliance.md), [`docs/threat-model.md`](docs/threat-model.md),
[`docs/cost-control.md`](docs/cost-control.md), [`docs/deployment.md`](docs/deployment.md).

```bash
cd backend
export OUTREACH_SENDER_NAME="Your Name" OUTREACH_SENDER_COMPANY="Your Company" \
       OUTREACH_SENDER_ADDRESS="1 rue Fictive, 69000 Lyon" OUTREACH_SENDER_EMAIL=you@example.com   # drafts need these
alembic upgrade head && python -m scripts.seed_demo && uvicorn server:app --port 8000 &
TOKEN=$(curl -s localhost:8000/api/auth/login -H 'content-type: application/json' \
  -d '{"email":"demo@clawpilot.io","password":"Demo12345!"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
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
observation never counts against a prospect. There is no UI for this yet (next slice).

Tests: `pytest tests/unit` runs offline with no server or database; `pytest tests/test_outreach_prospects.py` is the end-to-end
journey against a running server (needs the `OUTREACH_SENDER_*` variables above on the server).

## Webhook security

`POST /api/webhooks/twilio` verifies `X-Twilio-Signature` with `TWILIO_AUTH_TOKEN` and returns
403 otherwise, so nobody can forge replies or STOP opt-outs. It fails closed: with `APP_ENV=production`
and no token, every call is rejected. Without a token outside production (local mock mode) calls are
accepted unsigned, with a warning in the log. Set `TWILIO_WEBHOOK_URL` to the exact URL configured in
Twilio — behind a proxy the URL the app sees differs from the one Twilio signed.
`POST /api/webhooks/sendgrid` is **not** signed yet.

## Demo account

New accounts start **empty**. For local development, `python -m scripts.seed_demo`
(from `backend/`) creates `demo@clawpilot.io` / `Demo12345!` with sample leads and campaigns.
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

- **Frontend**: Netlify (already configured, see `frontend/public/netlify.toml`).
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
