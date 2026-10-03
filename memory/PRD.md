# Plantiers - OutreachOS (ex-ClawPilot) — PRD (historique)

## Original problem statement
Build a highly scalable, production-grade SaaS platform for automated global outreach powered by ClawPilot agents. Features: agent orchestration, multi-step campaign builder, lead scraping/enrichment, multi-channel messaging (email + WhatsApp), real-time analytics, AI-powered message generation (multi-language), CRM pipeline. Dark futuristic cyberpunk UI with neon cyan/purple/blue + Framer Motion animations.

## User choices (captured 2026-02)
- Stack adaptation: React + FastAPI + MongoDB (user option 1a)
- Billing: deferred — JWT auth only (option 2c)
- AI model: Gemini 3 Flash via Emergent Universal LLM key (option 3c)
- Messaging: Email (SendGrid) + WhatsApp (Twilio) — option 4b
- Scope: Full MVP (option 5a)

## Architecture
- **Backend** (FastAPI, modular): `/app/backend/server.py` mounts routers from `routes/` (auth, leads, campaigns, agents, messages, ai, analytics, settings). Service layer in `services/` (ai_svc, sendgrid_svc, twilio_svc, seed).
- **Database**: MongoDB via motor. Collections: `organizations`, `users`, `leads`, `campaigns`, `agents`, `messages`, `activity`.
- **Auth**: JWT (HS256) + bcrypt, multi-tenant org isolation on every query.
- **AI**: Gemini 3 Flash via `emergentintegrations` LlmChat.
- **Frontend**: React 19, React Router 7, Framer Motion, Recharts, Sonner, Phosphor icons. Cyberpunk theme with Chivo / IBM Plex Sans / JetBrains Mono fonts, neon cyan/purple/blue on #050505.

## Implemented (2026-02)
- JWT auth (register, login, me) with auto-seed of demo data on new org
- Leads CRM — table + kanban, search, stage transitions, enrichment simulation
- Campaigns — multi-step builder, launch simulator, pause/resume, status
- Agents orchestration — spawn, toggle, live logs, pulse/beam animations
- Multi-channel messaging — SendGrid (graceful mock if unverified sender), Twilio WhatsApp (graceful mock unless AC SID), composer with AI Write
- AI Composer — subject/body generation, multi-language (10 languages), tone + channel controls
- Analytics — 14-day timeseries, funnel, pipeline density, territories, channel mix
- Activity feed — real-time event stream (campaign, lead, agent events)
- Settings — org profile, integration health statuses

## Test status (iteration_1)
- Backend: 100% (37/37 tests)
- Frontend: 100% all UI flows
- Mock statuses for email/whatsapp are expected (user provided SK API key, not AC Account SID; SendGrid sender unverified)

## Seeded demo account
- email: demo@outreachos.example / password: Demo12345! — 12 leads, 4 agents, 4 campaigns, 8+ messages, 6+ activity events

## Backlog (P1)
- Real WhatsApp once user provides Twilio AC Account SID
- Verified SendGrid sender domain
- Webhook handlers for SendGrid (open/click) + Twilio (inbound replies)
- Background queue (Redis + BullMQ equivalent) for scheduled step-delays
- Billing (Stripe) when user turns it on
- Team members & RBAC UI (owner/admin/member already supported in model)
- Lead import (CSV), scraping connectors

## Backlog (P2)
- AI reply agent for inbound responses
- A/B testing for subject lines
- Real-time updates via WebSocket/SSE
- Advanced analytics (cohort, attribution)

## Iteration 2 (2026-02) — Light Theme + Feature Maximization

### Theme redesign
- Switched dark cyberpunk → **light gray gridded canvas** (`#EDEBE0` + 32px gridlines) with **ClawPilot red** (`#DC2626`) as primary accent, ink black (`#0F172A`) as secondary
- New utility classes: `.btn-ink`, `.chip-red`, `.dot-paper`, `.flash-pulse`
- White surfaces with solid 1px borders + subtle shadows; red-glow hover states

### Feature maximization
Backend additions:
- `POST /api/leads/bulk` — CSV-style bulk import with email dedup (`{created, skipped, errors, lead_ids}`)
- `POST /api/leads/bulk-stage` — bulk stage transitions
- `POST /api/messages/email/batch` — multi-lead dispatch with `{{first_name}}` `{{full_name}}` `{{company}}` `{{title}}` `{{country}}` token substitution; returns `{dispatched, sent, mocked, failed, skipped, total}`
- `POST /api/messages/whatsapp/batch` — same pattern for WhatsApp
- `POST /api/campaigns/{id}/assign-leads` — org-validated lead assignment
- `POST /api/campaigns/{id}/run-step/{index}` — executes one step against assigned leads with token rendering, returns rich result
- `POST /api/ai/generate/variants` — 3 tone variants (professional / friendly / urgent) in parallel via `asyncio.gather`

Frontend additions:
- `BulkLeadsModal` — paste/import multiple leads with live preview and result panel
- `BatchComposerModal` — lead multi-select, token hints, AI WRITE with tokenization, live preview, dispatch summary with sent/mocked/failed/skipped
- `CampaignDetailDrawer` — slide-in side drawer with metrics, lead assignment, and per-step RUN button with inline execution stats
- AI Composer — "GENERATE 3 VARIANTS" button with stacked tone cards you can click to adopt
- Messages page — "BATCH EMAIL" + "BATCH WHATSAPP" shortcuts
- Leads page — "BULK IMPORT" + "BATCH SEND" shortcuts + campaign lead-count chips

### Test status (iteration_2)
- Backend: 100% (28/28 tests pass)
- Frontend: 95% → fixed (renamed `open-{id}` → `view-campaign-{id}` to avoid testid collision with sidebar AI button)

## Iteration 3 (2026-07) — Rebrand + PostgreSQL/Celery migration

Full rebrand OpenClaw → ClawPilot (API title, logger, demo account, localStorage
token key, UI copy). Migrated the persistence layer from MongoDB to PostgreSQL
route by route (auth → leads → campaigns → messages/webhooks → analytics →
agents), keeping every existing HTTP contract identical — the 65 pre-existing
backend tests pass unmodified against the new stack. `settings` had no DB
dependency and needed no change.

### New architecture
- **Schema**: 23 tables (SQLAlchemy 2.0 async + Alembic) — `accounts`/`users`,
  `leads`/`lead_sources`/`lead_scores`/`contacts`, `consent_records`/`consent_current`,
  `campaigns`/`campaign_steps`/`campaign_leads`/`send_policies`,
  `outreach_events`/`email_sends`/`whatsapp_sends`, `webhook_events`,
  `segments`/`tags`/`lead_tags`, `notes`/`tasks`/`audit_logs`, `agents`.
- **Repository layer** (`backend/repositories/`): the only code that touches
  SQLAlchemy directly — routes call `account_repo`/`lead_repo`/`campaign_repo`/
  `outreach_repo`/`agent_repo`, never the ORM directly.
- **Real analytics**: the `/analytics/overview` 14-day timeseries is now built
  from real `outreach_events` rows instead of `random.seed(hash(org_id))`.
- **Data migration**: `backend/scripts/migrate_mongo_to_postgres.py` — one-shot,
  idempotent, reuses existing Mongo UUIDs as Postgres primary keys.
- **Still on Mongo (transitional)**: the `activity` feed / agent live-log
  simulation. Everything else has moved.
- **Infra**: `docker-compose.yml` (postgres, redis, mailpit, mongo, backend),
  `backend/Dockerfile`, `backend/.env.example`.
- **CI/CD**: `.github/workflows/ci.yml` — lint (black/isort/flake8, mypy
  informational), alembic drift check, integration tests against real
  Postgres+Redis+Mongo services, frontend build, Render deploy on `main`.

### Lead engine — compliance + scoring (same iteration, 2026-07)
- **Consent** (`repositories/consent_repo.py`): every lead gets a primary
  `Contact` at creation time; consent is tracked per-contact/per-channel in
  `consent_records` (append-only) + `consent_current` (hot-path read).
  Enforcement is deliberately asymmetric per the brief's own wording — WhatsApp
  requires an explicit `opted_in` record (strict), email only blocks on
  explicit `opted_out` (opt-out model). Enforced on every send path: single
  send, batch send, campaign run-step, and the scheduler.
  - Opt-in sources: `LeadCreate.email_opt_in`/`whatsapp_opt_in` (API, bulk
    import, CSV columns), or `POST /api/leads/{id}/consent` (manual).
  - Opt-out sources: SendGrid `unsubscribe` webhook event, or a WhatsApp reply
    matching a STOP/UNSUBSCRIBE/ARRET keyword (whole-word match only).
- **Scoring** (`services/scoring.py` + `repositories/lead_repo.py::rescore_lead`):
  real weighted scoring (title seniority, target country, tag/sector fit,
  lead-source intent, real engagement from `outreach_events`, inactivity
  decay) replaces the old random `/leads/enrich` bump. Computed at lead
  creation and on every `/leads/enrich` call; every recomputation is recorded
  in `lead_scores` with a human-readable factor breakdown. Weights are hardcoded
  defaults — the natural next step is making them configurable per account.

### Not yet done (see backlog)
- Celery/Redis workers (queues defined in the architecture plan, not yet wired
  up — `services/scheduler.py` still runs the in-process asyncio poll loop).
- Throttling + per-timezone send windows.
- Configurable scoring weights, A/B testing depth, CRM (notes/tasks/tags UI).
