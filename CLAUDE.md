# CLAUDE.md — ClawPilot

Plateforme de génération de leads B2B et d'outreach multicanal (email / WhatsApp) :
sourcing → enrichissement → scoring → séquences → suivi des réponses. Voir `README.md`
pour l'installation et `docs/cloud-sessions.md` pour la feuille de route en cours.

## Stack

- Backend : Python 3.12, FastAPI, SQLAlchemy 2.0 async + Alembic, PostgreSQL 16
- Jobs : Celery 5 + Redis (3 files : `sends`, `automation`, `webhooks`), planification via Celery beat
- Frontend : React 19 en **JavaScript** (CRA/craco, Tailwind, Radix/shadcn) — ne pas migrer vers TypeScript
- Envoi : SendGrid (email), Twilio (WhatsApp). Chaque intégration externe a un mode « mock » sans clé.
- Ne pas introduire Next.js, Prisma ou Drizzle : la stack est tranchée (option A).

## Architecture — règles à respecter

- `backend/repositories/` est la **seule** couche qui touche SQLAlchemy. Les routes sont fines et appellent les repos.
- `backend/models.py` (Pydantic) = contrat HTTP. `backend/db/models/` (ORM) = stockage. Ne pas les mélanger.
- Une intégration externe = un module `backend/services/<nom>_svc.py` avec `is_configured()` et un repli propre
  (statut `not_configured` / `mock`) quand la clé est absente ou que le plan du fournisseur refuse l'appel.
- Tâches Celery : wrappers synchrones autour des repos async via `tasks/_bridge.run_async`. Toute nouvelle
  tâche doit être déclarée dans `include=[...]` de `celery_app.py` (pas d'autodiscover).
- Tout changement de schéma = migration Alembic. `alembic check` doit rester vert.
  - Alembic **ne détecte pas** les changements de contrainte CHECK : écrire la migration à la main.
  - Les contraintes sont nommées avec un nom **court** (`"kind"`) : la convention de nommage ajoute le préfixe
    `ck_<table>_`. Passer le nom complet le double (`ck_x_ck_x_kind`).
- Tables d'événements (`outreach_events`, `email_sends`, `consent_records`, `audit_logs`, `lead_scores`) : append-only,
  jamais de suppression logique. Les tables métier utilisent `deleted_at`.

## Conformité (non négociable)

- Consentement : WhatsApp = opt-in explicite requis. Email = bloqué uniquement si `opted_out`. Passer par
  `consent_repo.can_send(...)` avant tout envoi.
- Tout email sortant contient : identité de l'expéditeur, origine des données, lien de désinscription fonctionnel.
- Tout webhook public (Twilio, SendGrid…) vérifie la signature du fournisseur avant de toucher à la base,
  et échoue fermé en production quand la clé de vérification est absente.
- Un prospect de la découverte (`leads.review_status` non NULL) n'est contactable que s'il est `approved` **et** si
  `FEATURE_LIVE_SENDING=true`. Tout nouveau chemin d'envoi passe par `lead_repo.get_leads_by_ids` ou
  `discovery_send_block`. Un brouillon n'affirme que des faits portés par un signal `detected` (jamais d'invention).
  `unknown` n'est jamais traité comme un défaut.
- Pas de scraping contraire aux CGU des plateformes ni à `robots.txt`. Pas d'envoi de masse non consenti.
- Jamais de clé ou secret dans le code, les tests, les logs ou un commit. `backend/.env` est ignoré par git ;
  toute nouvelle variable est ajoutée à `backend/.env.example` **et** au README.

## Commandes

Toutes depuis `backend/` sauf mention contraire.

```bash
# Lint (flags identiques à la CI — ne JAMAIS lancer black/isort depuis la racine : ils reformatent .venv)
black --check --line-length 120 --extend-exclude "alembic/versions" .
isort --check-only .
flake8 .
mypy --ignore-missing-imports db/ repositories/ routes/ services/ deps.py models.py   # informatif

# Migrations
alembic upgrade head && alembic check

# Tests d'intégration : un serveur doit tourner (voir .github/workflows/ci.yml pour la séquence exacte)
uvicorn server:app --port 8000 &
REACT_APP_BACKEND_URL=http://localhost:8000 pytest tests/ -v

# Worker et beat (si la tâche touche Celery)
celery -A celery_app worker -Q sends,automation,webhooks -l info
celery -A celery_app beat -l info
```

```bash
# frontend/
npm ci --legacy-peer-deps      # conflit de peer deps date-fns / react-day-picker, connu
npm run lint && npm run build
```

## Découverte (OutreachOS)

- Logique pure dans `backend/services/outreach_os/` (sans I/O, `now` injecté) ; seul `pipeline.py` parle à la base, via les
  repositories. Sources et analyseurs = `Protocol` ; seules des fixtures locales existent. Aucune source réseau sans
  `FEATURE_EXTERNAL_SOURCES`, `robots.txt` et CGU vérifiés. `mypy --strict --follow-imports=silent services/outreach_os` doit
  rester propre. Voir `docs/architecture.md`.

## Tests

- Logique pure (parsers, détecteurs de signaux, scoring, rendu de templates) → tests unitaires dans
  `backend/tests/unit/` (`pytest tests/unit`), **sans serveur ni réseau**, avec des fixtures (HTML, JSON) versionnées.
- Aucun appel réseau réel dans les tests, jamais. Les appels sortants sont mockés ou rejoués depuis des fixtures.
- Chaque endpoint ajouté est couvert par un test d'intégration dans `backend/tests/`. Les tests existants restent verts.

## Git

- Une fonctionnalité = une branche `feat/<nom>` = une PR, avec ses tests. Hors fonctionnalité : `fix/`, `chore/`, `docs/`.
- Commits conventionnels : `feat(scope): ...`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`.
- Ne jamais pousser sur `main`. La PR décrit ce qui a été fait, ce qui reste à brancher et comment le vérifier.
