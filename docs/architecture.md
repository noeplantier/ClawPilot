# Architecture — OutreachOS (découverte → score → revue → brouillon)

Stack inchangée : FastAPI, SQLAlchemy 2 async + Alembic, PostgreSQL, Celery/Redis, React (JavaScript).
Cette page décrit la tranche « parcours vertical » ; le reste de la plateforme est décrit dans le README.

## Flux (tout est en dry-run : rien n'est envoyé)

```
SourceAdapter ──► normalisation ──► déduplication ──► SiteFetcher ──► signaux ──► score ──► revue humaine ──► brouillon
 (fixtures)       nom/tél/domaine    clés communes      (fixtures)    3 états    0–100     approuver/rejeter    e-mail + conformité
                                                                          │         │                │                 │
                                                                          └─────────┴── tables append-only + audit_logs + usage_records
```

## Modules

| Couche | Fichiers | Règle |
|---|---|---|
| Logique pure | `backend/services/outreach_os/{types,normalize,dedupe,sources,signals,scoring,drafts,unsubscribe}.py` | Aucune I/O, aucune horloge (le `now` est injecté). `mypy --strict` propre. |
| Orchestration | `services/outreach_os/pipeline.py` | Seul module du paquet qui parle à la base, via les repositories. |
| Accès base | `repositories/{prospect,suppression,draft,usage}_repo.py` | Seule couche qui touche SQLAlchemy. |
| HTTP | `routes/prospects.py`, `routes/unsubscribe.py`, contrat dans `models.py` | Routes fines. Lecture : tout membre. Décisions (valider, effacer, configurer) : `owner`/`admin`. |
| Drapeaux | `services/feature_flags.py` | Tout est éteint par défaut. |

Les sources et analyseurs sont des `Protocol` (`SourceAdapter`, `SiteFetcher`, `MobileAnalyzer`) : les tests et le mode
dry-run utilisent des fixtures locales (`backend/fixtures/restaurants_demo/`). Aucune implémentation réseau n'existe.

## Modèle de données

Réutilisé : `accounts` (Organization), `users`, `leads` (= Prospect), `contacts`, `consent_*`, `campaigns`/`campaign_steps`,
`audit_logs`. Détail des colonnes : [`schema.md`](schema.md) (généré).

| Concept | Table | Nature |
|---|---|---|
| Prospect | `leads` + `vertical, city, website, match_keys, review_status` | `review_status` NULL = lead CRM hors découverte |
| ProspectSource | `prospect_sources` | append-only ; un enregistrement par (annonce, version du contenu) ; licence et date |
| ProspectSignal | `prospect_signals` | append-only ; état courant = dernière ligne par signal ; CHECK `unknown/detected/not_detected` |
| ScoreVersion | `score_versions` | immuable ; chaque changement = nouvelle version ; la plus haute est active |
| (historique) | `prospect_scores` | append-only ; score 0–100, couverture, détail par signal |
| MessageDraft | `message_drafts` | statut `draft/approved/rejected`, clé d'idempotence unique par organisation |
| SuppressionEntry | `suppression_entries` | empreintes SHA-256, par organisation |
| UsageRecord | `usage_records` | append-only ; mesure pour [`cost-control.md`](cost-control.md) |
| AuditLog | `audit_logs` | existant ; chaque action sensible y écrit |

`prospect_scores` est distinct de `lead_scores` : le second note l'adéquation de profil CRM (`services/scoring.py`), le premier le
besoin digital. Les deux coexistent.

## Score

`points(signal) = poids` si le signal est `detected`, sinon 0. Score = somme bornée à [0, 100]. `unknown` et `not_detected`
ne retranchent ni n'ajoutent rien. `coverage` = part des signaux pondérés réellement observés : un score bas avec une couverture
basse signifie « information insuffisante », pas « mauvais prospect ». Les poids sont configurables
(`PUT /api/prospects/score-config`) ; la configuration est hachée et versionnée ; modifier la config recalcule à partir des signaux
stockés, sans nouvelle observation. `stale_days` n'agit qu'au prochain run (la péremption est observée à l'analyse).

## Garde-fous d'envoi

Les prospects de la découverte sont dans `leads`, donc atteignables par les anciens chemins d'envoi. Deux points de passage
(`lead_repo.get_leads_by_ids`, `routes/messages._enforce_consent_for_lead`) refusent tout prospect qui n'est pas **approuvé**,
et **tous** tant que `FEATURE_LIVE_SENDING` est éteint. Le refus est journalisé (`send.blocked_review`).

## Non implémenté (volontairement)

Adapter d'envoi (`ChannelAdapter`), quotas et délais réels, bounces/réponses de ce parcours, source réseau, interface React
(tranche suivante). Détails dans la feuille de route.
