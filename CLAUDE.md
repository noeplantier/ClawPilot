# CLAUDE.md — Plantiers - OutreachOS

Plateforme de génération de leads B2B et d'outreach multicanal (email / WhatsApp) :
sourcing → enrichissement → scoring → séquences → suivi des réponses. Voir `README.md`
pour l'installation et `docs/cloud-sessions.md` pour la feuille de route en cours.

## Stack

- Backend : Python 3.12, FastAPI, SQLAlchemy 2.0 async + Alembic, PostgreSQL 16
- Jobs : Celery 5 + Redis (3 files : `sends`, `automation`, `webhooks`), planification via Celery beat
- Frontend : React 19 en **JavaScript** (CRA/craco, Tailwind, Radix/shadcn) — ne pas migrer vers TypeScript
- Envoi : SMTP puis SendGrid (email), Twilio (WhatsApp). Une intégration non configurée **refuse et dit quoi configurer** : jamais de
  statut « mock », d'envoi simulé ni de texte tout fait (`services/mail_provider.py`). Seul `OUTREACH_TEST_SINK` (tests, jamais en production) enregistre sans envoyer.
- Ne pas introduire Next.js, Prisma ou Drizzle : la stack est tranchée (option A).

## Architecture — règles à respecter

- `backend/repositories/` est la **seule** couche qui touche SQLAlchemy. Les routes sont fines et appellent les repos.
- `backend/models.py` (Pydantic) = contrat HTTP. `backend/db/models/` (ORM) = stockage. Ne pas les mélanger.
- Une intégration externe = un module `backend/services/<nom>_svc.py` avec `is_configured()` et un refus explicite
  (`not_configured`, jamais un faux succès) quand la clé est absente ou que le plan du fournisseur refuse l'appel.
- Settings > Integrations : le statut de chaque intégration est calculé côté serveur (`services/integrations_status.py`, pur) et ne renvoie que des
  **noms** de variables, jamais une valeur. Une nouvelle intégration = une entrée du catalogue + ses variables dans `TRACKED_ENV` + une fiche dans
  `docs/integrations.md` ; son test réel (`services/integration_checks.py`) est en lecture seule et n'envoie rien à une personne.
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
- Tout envoi sortant passe par un `ChannelAdapter` (`services/outreach_os/channels.py`) via
  `services/outreach_os/dispatch.py` : kill switch (`SEND_KILL_SWITCH`), pause du compte, limites (jour, heure, délai),
  conformité du contenu, idempotence. Les anciens chemins (envoi unitaire, lot, campagne, tâches Celery) appellent le même
  point d'application, `services/send_gate.py` (`send_gate.check` **avant** `send_email`/`send_whatsapp` ; un test AST
  l'impose). Tout nouveau chemin d'envoi passe par là. L'adaptateur réel (SMTP, `services/smtp_svc.py`) est injecté dans
  `dispatch_draft` ; activer `FEATURE_LIVE_SENDING` sans `SMTP_*` complet doit échouer (fail closed), le sandbox
  (`OUTREACH_SANDBOX`, `OUTREACH_LIVE_ALLOWLIST`) est actif par défaut, et la ligne `sending` est validée **avant** l'appel du
  fournisseur (au plus une fois ; issue inconnue = jamais de renvoi automatique). Voir `docs/go-live-email.md`. Un refus
  est journalisé **avant** de lever l'`HTTPException` (`get_db_session` annule la transaction sur erreur).
- Journal d'événements : horodater avec `clock_timestamp()`, pas `now()`, quand plusieurs lignes d'une même transaction
  doivent garder leur ordre.
- Pas de scraping contraire aux CGU des plateformes ni à `robots.txt`. Pas d'envoi de masse non consenti.
- Jamais de clé ou secret dans le code, les tests, les logs ou un commit. `backend/.env` est ignoré par git ;
  toute nouvelle variable est ajoutée à `backend/.env.example` **et** au README.

## Commandes

Installation : `pip install -r requirements-dev.txt` (runtime + outils). L'image Docker n'installe que `requirements.txt`.

Toutes depuis `backend/` sauf mention contraire.

```bash
# Dépendances : éditer requirements.in / requirements-dev.in puis régénérer les locks (voir README « Dependencies »)
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
npm run lint && npm test -- --watchAll=false && npm run build
npm run e2e                    # Playwright, API réelle démarrée + build avec REACT_APP_BACKEND_URL (voir README « Tests »)
```

## Découverte (OutreachOS)

- Logique pure dans `backend/services/outreach_os/` (sans I/O, `now` injecté) ; seul `pipeline.py` parle à la base, via les
  repositories. Sources et analyseurs = `Protocol` ; seules des fixtures locales et les listes importées par un humain (`importer.py`, derrière `FEATURE_PROSPECT_IMPORT`, origine et base légale obligatoires, cellule vide = `unknown`) existent. Aucune source réseau sans
  `FEATURE_EXTERNAL_SOURCES`, `robots.txt` et CGU vérifiés. `mypy --strict --follow-imports=silent services/outreach_os` doit
  rester propre. Voir `docs/architecture.md`.

## Interface OutreachOS (frontend)

- Écrans dans `frontend/src/pages/{Prospects,ProspectDetail,ReviewQueue,Sending}.jsx`, composants dans
  `components/outreach/`, appels API dans `lib/outreach.js`, formatage pur dans `lib/outreachFormat.js` (testé).
- Design : prolongement de plantiers.com (fond `#07060B`, violet `#7C3AED`, Inter + JetBrains Mono auto-hébergées, logo `components/Logo.jsx`). Les écrans
  n'écrivent aucune couleur dans une classe : tokens de `index.css` (`text-soft`, `text-faint`, `bg-card`, `border-border`, `brand-*`) ; `src/theme.test.js` le vérifie.
  Voir `docs/design-system.md`.
- Aucune donnée inventée : un chiffre vient de l'API, sinon un état vide explicite (« not scored » ≠ 0). Un état
  `unknown` s'affiche comme tel et ne vaut jamais un défaut. Ne pas coder en dur un statut d'intégration.
- Chaleur : TOP (≥ 80) et lead vide (ni e-mail, ni téléphone, ni site) sont décidés par le serveur (`heat.top`, `heat.has_contact`, jumeau SQL dans
  `heat_sql.py`) ; l'interface ne recalcule rien et ne masque un lead que sur `has_contact === false`. Voir `docs/scoring.md`.
- Recherche de ville de la carte : `components/outreach/CityBox.jsx` + `lib/cityComplete.js` (pur, testé). Les compteurs de leads par ville
  viennent de `GET /api/map/cities` (jumeau SQL de la chaleur, `repositories/prospect_repo.city_heat_rows`), jamais recalculés dans le
  navigateur ; sans compteurs chargés, rien n'est affiché (pas de 0 inventé). Voir `docs/map-search.md`.
- Tests Jest sans dépendance ajoutée (`react-dom/client` + `act`, API mockée) ; l'alias `@/` et react-router v7 sont
  mappés dans `craco.config.js` (le Jest 27 de CRA ignore le champ `exports`).

## Tests

- Logique pure (parsers, détecteurs de signaux, scoring, rendu de templates) → tests unitaires dans
  `backend/tests/unit/` (`pytest tests/unit`), **sans serveur ni réseau**, avec des fixtures (HTML, JSON) versionnées.
- Aucun appel réseau réel dans les tests, jamais. Les appels sortants sont mockés ou rejoués depuis des fixtures.
- Chaque endpoint ajouté est couvert par un test d'intégration dans `backend/tests/`. Les tests existants restent verts.

## Git

- Une fonctionnalité = une branche `feat/<nom>` = une PR, avec ses tests. Hors fonctionnalité : `fix/`, `chore/`, `docs/`.
- Commits conventionnels : `feat(scope): ...`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`.
- Ne jamais pousser sur `main`. La PR décrit ce qui a été fait, ce qui reste à brancher et comment le vérifier.
