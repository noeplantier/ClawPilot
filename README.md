# ClawPilot

B2B lead-generation and multi-channel outreach platform: lead ingestion, scoring,
email/WhatsApp sequences, CRM pipeline, analytics, and automation — built to run
autonomously with human oversight.

## Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0 (async) + Alembic, PostgreSQL
- **Legacy (transitional)**: MongoDB still backs the activity feed and agent live-log
  simulation — see [`memory/PRD.md`](memory/PRD.md) for the migration status
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
    migrate_mongo_to_postgres.py   one-shot legacy data migration
  tests/                 Backend integration test suite (pytest)
frontend/
  src/                   React app (pages, components, contexts, lib)
docker-compose.yml       Postgres, Redis, Mailpit, Mongo (transitional), backend
.github/workflows/ci.yml Lint, migration check, tests, build, deploy
```

## Local development

### Option A — Docker Compose

```bash
cp backend/.env.example backend/.env      # fill in secrets as needed
docker compose up --build
cd backend && alembic upgrade head        # first run only
```

Backend: http://localhost:8000/api/health · Mailpit (test emails): http://localhost:8025

### Option B — native (Postgres/Redis/Mongo installed locally)

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                      # set DATABASE_URL, MONGO_URL, JWT_SECRET, ...
alembic upgrade head
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
required to boot in a degraded/mock mode except `DATABASE_URL`, `MONGO_URL`,
`DB_NAME`, and `JWT_SECRET` — SendGrid/Twilio/AI all fall back to graceful mocks
when unconfigured.

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

## Migrating existing MongoDB data

One-shot, idempotent — safe to re-run:

```bash
cd backend
python scripts/migrate_mongo_to_postgres.py --dry-run   # preview counts first
python scripts/migrate_mongo_to_postgres.py
```

## Deployment

- **Frontend**: Netlify (already configured, see `frontend/public/netlify.toml`).
- **Backend**: Docker image via `backend/Dockerfile`, deployed to Render. CI
  triggers a deploy on every push to `main` via `RENDER_DEPLOY_HOOK_URL` (repo
  secret) once tests and the frontend build pass.
- Provision managed PostgreSQL + Redis on Render (or your host of choice) and
  point `DATABASE_URL` / `REDIS_URL` at them; run `alembic upgrade head` as a
  release step.

## Status & roadmap

Implemented: Postgres schema, consent tracking and enforcement, weighted lead scoring,
Celery-based throttled sends with send windows, CRM (notes, tasks, tags, kanban),
real analytics. See [`memory/PRD.md`](memory/PRD.md) for the detailed history.

Next: automatic prospect sourcing for local businesses, digital-gap scoring, per-vertical
email sequences with reply detection, and an inbox view — broken down into short,
independent work sessions in [`docs/cloud-sessions.md`](docs/cloud-sessions.md).
