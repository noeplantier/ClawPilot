# OpenClaw — Outreach SaaS Platform · PRD

## Original problem statement
Build a highly scalable, production-grade SaaS platform for automated global outreach powered by OpenClaw agents. Features: agent orchestration, multi-step campaign builder, lead scraping/enrichment, multi-channel messaging (email + WhatsApp), real-time analytics, AI-powered message generation (multi-language), CRM pipeline. Dark futuristic cyberpunk UI with neon cyan/purple/blue + Framer Motion animations.

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
- email: demo@openclaw.io / password: Demo12345! — 12 leads, 4 agents, 4 campaigns, 8+ messages, 6+ activity events

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
