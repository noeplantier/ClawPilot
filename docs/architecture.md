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
| OutboundMessage / OutboundEvent | `outbound_messages`, `outbound_events` | journal d'envoi (dry-run) ; événements append-only, `status` avance avec rebonds et réponses |
| Limites d'envoi | `send_policies` (`max_per_day`, `max_per_hour`, `min_delay_seconds`, `sending_paused`) | par organisation et par canal ; `max_per_hour` existait mais n'était lu nulle part, il est maintenant appliqué au dispatch |
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

## Envoi contrôlé (dry-run)

```
brouillon approuvé ─► dispatch ─► kill switch ─► pause du compte ─► éligibilité ─► suppression/consentement ─► conformité ─► limites ─► adaptateur ─► sandbox ─► ligne `sending` (validée) ─► ChannelAdapter ─► `sent` | `failed` | reste `sending`
                                                                                                                                  │
                                                          outbound_messages + outbound_events + audit_logs + usage_records ◄─────┘
```

| Élément | Fichier | Rôle |
|---|---|---|
| `ChannelAdapter` (Protocol), `DryRunEmailAdapter`, `select_adapter` | `services/outreach_os/channels.py` | Seul endroit d'où un message peut sortir. L'adaptateur dry-run n'ouvre aucun socket. L'adaptateur réel est **injecté** par l'appelant (le module reste sans E/S) ; `FEATURE_LIVE_SENDING` sans adaptateur configuré ⇒ refus (501). |
| `SmtpEmailAdapter`, `SmtpConfig`, `build_message` | `services/smtp_svc.py` | Intégration SMTP (`smtplib`) : TLS vérifié obligatoire, délais, erreurs classées (`failed` / `unknown`), mot de passe jamais exposé, liste blanche du sandbox rappelée avant la connexion. |
| `is_allowed`, `parse_allowlist` | `services/outreach_os/sandbox.py` | Liste blanche du sandbox, pure : adresse ou `@domaine`, liste vide = personne. |
| `evaluate` | `services/outreach_os/limits.py` | Plafond quotidien, plafond horaire glissant, délai minimum ; pur, horloge injectée. |
| `send_gate` (`check`, `status`) | `services/send_gate.py` | Point d'application unique avant tout fournisseur : kill switch, pause, plafonds. Compte les envois de **tous** les chemins (`outbound_messages`, `email_sends`, `whatsapp_sends`) et sérialise les envoyeurs concurrents par verrou consultatif (organisation × canal). Utilisé par `dispatch`, `routes/messages.py`, `routes/campaigns.py` et `tasks/send_tasks.py`. |
| `is_opt_out` | `services/outreach_os/replies.py` | Détecte un STOP/désinscription dans une réponse (FR/EN, sans faux positif sur « non-stop »). |
| `dispatch_draft`, `simulate_event` | `services/outreach_os/dispatch.py` | Orchestration ; seule couche à écrire en base, via les repositories. |
| `/api/outbound/*` | `routes/outbound.py` | dispatch, liste, détail, simulation, limites, statut. |

Le journal `outbound_messages` / `outbound_events` est **séparé** de `email_sends` / `outreach_events` : ces derniers alimentent
les analytics, et un envoi simulé ne doit jamais y apparaître comme un message délivré. L'adaptateur SMTP n'écrit que dans le journal `outbound_*` ; `POST /outbound/test-send` écrit dans `email_sends` (pour compter dans les limites), sans événement d'outreach.
`outbound_events` utilise `clock_timestamp()` pour garder l'ordre de plusieurs événements écrits dans une même transaction.

Réponses et rebonds : simulés par `POST /outbound/{id}/simulate` (même code que les webhooks fournisseur). Un rebond dur suspend
l'adresse ; une réponse STOP désinscrit le prospect immédiatement, via le même chemin que le lien de désinscription.

## Interface (React, JavaScript)

| Écran | Fichier | Données (API) |
|---|---|---|
| Liste, filtres, découverte | `pages/Prospects.jsx` | `GET /prospects`, `POST /prospects/discovery/run` |
| Détail, justification du score, signaux, provenance, historique, brouillons, effacement | `pages/ProspectDetail.jsx` + `components/outreach/*` | `GET /prospects/{id}`, `/events`, `/outbound`, `/outbound/{id}`, `/outbound/status` |
| File de revue | `pages/ReviewQueue.jsx` | `GET /prospects?review_status=pending`, `POST /prospects/{id}/review` |
| Limites, statut, historique d'envoi | `pages/Sending.jsx` | `/outbound/status`, `/outbound/limits`, `/outbound`, `/prospects/settings` |

Règles : aucune valeur fictive (un chiffre vient de l'API, sinon un état vide explicite) ; `unknown` n'est jamais présenté
comme un défaut ; l'état n'est jamais porté par la seule couleur (glyphe + mot) ; les actions de décision sont désactivées pour
un rôle `member` (l'API refuse de toute façon). Logique de présentation pure dans `lib/outreachFormat.js`, testée sans navigateur.

## Non implémenté (volontairement)

Adaptateur d'envoi réel (SMTP/SendGrid) et ses prérequis (voir `deployment.md`), webhooks de réponse/rebond branchés sur
`outbound_*`, relances automatiques (séquences), WhatsApp, source réseau, éditeur des poids du score dans l'interface (l'API existe),
pagination de l'historique, rôle `member` testé de bout en bout.
