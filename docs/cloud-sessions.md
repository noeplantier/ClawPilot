# Feuille de route cloud — option A (FastAPI conservé)

Objectif : transformer ClawPilot en machine de prospection pour commerces locaux
(sourcing → enrichissement → scoring par signaux → séquence email → suivi des réponses),
**sans réécrire le socle existant** (Postgres, consentement, Celery, CRM, CI).

## Avant de lancer une session

1. Merger la PR qui contient `CLAUDE.md`, le README mis à jour et ce fichier. Les sessions cloud
   clonent GitHub : sans cela elles ne verront pas les règles du projet.
2. (Optionnel) créer les issues à partir des blocs « Issue » ci-dessous.
3. Lancer les sessions **dans l'ordre, une à la fois, en mergeant chaque PR avant la suivante**.
   Les migrations Alembic forment une chaîne linéaire : deux sessions en parallèle créent deux
   « heads » et cassent `alembic upgrade head`.

## Budget

| Session | Mission | ≈ $ |
|---|---|---|
| S1 | Hygiène & dette (Mongo, connexion démo, schéma, déploiement) | 8 |
| S2 | Sourcing & signaux digitaux + formulaire inbound | 22 |
| S3 | Scoring par signaux, pondérations configurables | 10 |
| S4 | Email : SMTP, séquences par vertical, réponses, désinscription | 20 |
| S5 | Dashboard : filtres, score expliqué, Inbox | 15 |
| S6 | Durcissement, E2E, déploiement | 10 |
| | **Total** | **85** |

Marge de 15 $ pour relancer une session qui part de travers.

## Écarts par rapport au kit d'origine

- **Pas de réécriture Next.js.** La table `leads` joue le rôle de `prospects` : campagnes, CRM, consentement
  et scoring en dépendent déjà. Une table parallèle dupliquerait tout cela.
- **Gmail OAuth reporté.** V1 = SMTP (envoi) + IMAP (détection des réponses). Gmail OAuth impose la
  vérification Google des scopes sensibles ; à ajouter plus tard derrière la même interface.
- **Signal « activité Instagram » retiré** : il exigerait de scraper Instagram, contraire à ses CGU.
- **Apollo hors plan.** Il vise les décideurs de sociétés SaaS, pas les restaurateurs ou artisans, et
  l'API est inaccessible sur le plan gratuit. L'interface `SourceAdapter` (S2) permettra de l'ajouter.
- **Quota d'envoi réellement appliqué.** Aujourd'hui `send_policies.max_per_hour` n'est lu nulle part :
  seule une limite fixe par worker existe. S4 corrige cela.

---

## S1 — Hygiène & dette

**Issue** — `[CHORE] Supprimer MongoDB, retirer la connexion démo, documenter le schéma, préparer Render`
Livrable : plus aucune dépendance Mongo, `docs/schema.md`, `render.yaml`, tests existants verts.

```
Mission : issue « Hygiène & dette ». Lis CLAUDE.md d'abord. Branche chore/hygiene.
Périmètre exact, rien d'autre :
1. Supprimer MongoDB. Le fil d'activité (db.activity, helper _log() dupliqué dans les routes) et le
   journal live des agents passent sur PostgreSQL via UN repository, en conservant la forme JSON de
   GET /api/analytics/activity et des routes agents. Retirer motor/pymongo/mongomock des dépendances,
   deps.db, MONGO_URL et DB_NAME de .env.example, du README, de docker-compose.yml et de la CI.
   Supprimer scripts/migrate_mongo_to_postgres.py (l'historique git le conserve).
2. Retirer le contournement client « bypass-token-12345 » (Login.jsx, AuthContext.jsx, lib/api.js).
   Le compte démo reste utilisable par une vraie connexion : ajoute scripts/seed_demo.py (idempotent)
   et documente-le dans le README.
3. Générer docs/schema.md (tables, colonnes, contraintes, relations) avec un script
   scripts/gen_schema_doc.py qui le régénère depuis les modèles ORM.
4. Ajouter render.yaml (web FastAPI, worker Celery, beat, Postgres, Redis ; alembic upgrade head en
   release step) et lister les variables d'environnement dans le README.
Contraintes : tous les tests existants restent verts sans MongoDB, alembic check vert, npm run lint et
npm run build verts. Termine par : commit propre, push, PR listant les fichiers supprimés et ce qui
change pour un développeur (setup local, connexion démo).
```

---

## S2 — Sourcing & signaux digitaux

**Issue** — `[SOURCING] Moteur de sourcing multi-sources, enrichissement, signaux de manque digital`
Livrable : `backend/services/sourcing/`, CLI `python -m scripts.scrape`, route publique d'entrée, tests sur fixtures.

```
Mission : issue « Sourcing ». Lis CLAUDE.md d'abord. Branche feat/sourcing. S1 est mergée.
Utilise la table leads comme table de prospects. Migration Alembic minimale (justifie chaque ajout
dans la PR) : leads.vertical, leads.city, leads.website, leads.external_id (index unique partiel par
compte, hors supprimés, hors NULL), leads.signals (JSONB, défaut '{}'), leads.sourced_at ; et la valeur
'inbound' dans la contrainte CHECK de lead_sources.kind (migration écrite à la main, nom court).

Structure : backend/services/sourcing/
- base.py : interface SourceAdapter (fetch(vertical, city, limit) -> list[RawProspect]).
- Adaptateur 1 : SerpAPI Google Maps (clé SERPAPI_API_KEY, ajoutée à .env.example). Avant de coder,
  vérifie les CGU de SerpAPI / Google sur la conservation des données et note la décision dans
  docs/sourcing.md. Ne stocke que ce que ces CGU permettent (identité de l'entreprise, adresse, site,
  téléphone, notes et dates d'avis utilisées comme signaux).
- enrichment.py : à partir du site PROPRE de l'entreprise (page d'accueil + page contact seulement) :
  extraire l'email public (mailto, texte visible), le titre et la description de la page. Respecter
  robots.txt, User-Agent identifiable, 1 requête/s par hôte, timeout 10 s. Aucun scraping de réseaux
  sociaux ni de page derrière un login.
- signals.py : détecteurs purs (html, en-têtes, données source) -> liste de Signal(code, label,
  evidence) : no_website, website_unreachable, not_responsive (pas de meta viewport, largeur fixe),
  no_online_booking (aucun lien vers un prestataire de réservation connu, aucun mot-clé de
  réservation), listing_inactive (peu d'avis récents ou fiche sans photos), owner_not_replying.
  Règle : une donnée absente = « inconnu », jamais un signal négatif.
- dedup : par external_id, puis domaine du site, puis email.
CLI : cd backend && python -m scripts.scrape --vertical=restaurant --city=Marseille --limit=20
[--dry-run]. Limite par défaut 20 (protège les crédits), --dry-run n'écrit rien en base.
Route publique POST /api/public/leads/{account_id} (sans auth) : validation Pydantic, champ piège
« website » (rempli => 200 silencieux, aucun lead), dédup par email, consentement email opt-in avec
consent_source « inbound_form », source « inbound_form » (kind inbound), 404 si compte inconnu.
Tests : unitaires dans backend/tests/unit/ avec fixtures HTML/JSON versionnées, AUCUN appel réseau ;
intégration pour la route publique. Vérifie que cd backend && pytest tests/unit tourne sans serveur
(ajoute pythonpath = . dans un pytest.ini si nécessaire).
Livrable : tests verts, PR listant les sources couvertes, les signaux détectables et ceux volontairement exclus.
```

---

## S3 — Scoring par signaux

**Issue** — `[SCORING] Score 0–100 expliqué à partir des signaux digitaux, pondérations configurables`
Livrable : profil de scoring `local_business`, config externe, détail par facteur, endpoints.

```
Mission : issue « Scoring ». Lis CLAUDE.md d'abord. Branche feat/scoring. S2 est mergée.
Étends backend/services/scoring.py sans casser l'existant : le profil B2B actuel (titres, pays, tags,
engagement) reste inchangé et tous les tests existants restent verts. Ajoute un profil local_business,
activé quand lead.vertical est renseigné, qui note les signaux de leads.signals (absence de site = poids
fort, site non responsive, pas de réservation en ligne, fiche inactive, avis récents sans réponse du
propriétaire = fort signal d'achat) plus l'engagement existant.
- Pondérations dans un fichier de config commenté (backend/config/scoring.toml, lu avec tomllib de la
  bibliothèque standard), plus aucune constante de poids en dur pour le nouveau profil.
- Justification structurée : migration ajoutant lead_scores.factors (JSONB nullable) contenant la liste
  {code, label, points}. L'API renvoie le détail par facteur.
- Endpoints : POST /api/leads/{id}/score et POST /api/campaigns/{id}/rescore (ownership vérifié).
- Tests unitaires exhaustifs : prospect sans site, prospect avec tous les signaux, aucun signal connu,
  signaux inconnus (ne pénalisent pas), plafonds 0 et 100.
Livrable : tests verts, PR contenant 3 exemples de scores justifiés (JSON complet) dans la description.
```

---

## S4 — Email : SMTP, séquences, réponses, désinscription

**Issue** — `[EMAIL] Séquences par vertical, envoi SMTP avec quota réel, détection des réponses, désinscription`
Livrable : fournisseur SMTP à côté de SendGrid, templates éditables, IMAP, désinscription publique, tests mockés.

```
Mission : issue « Email ». Lis CLAUDE.md d'abord. Branche feat/email. S3 est mergée. Réutilise l'existant
(consentement, Celery, send_policies) : ne réécris pas sourcing ni scoring.
1. Abstraction de fournisseur : backend/services/email_providers/ avec SendGrid (existant, déplacé sans
   changer son comportement) et SMTP (smtplib, variables SMTP_HOST/PORT/USER/PASSWORD/FROM dans
   .env.example). Génère toi-même le Message-ID de chaque envoi SMTP et stocke-le.
2. Quota réel : migration ajoutant send_policies.max_per_day (défaut 20). Aujourd'hui max_per_hour n'est
   lu nulle part : applique le quota journalier ET horaire dans la tâche d'envoi (au-delà, replanifier
   au prochain créneau avec self.retry(eta=...), max_retries=None). Ajoute une gigue aléatoire
   configurable dans les créneaux d'envoi.
3. Séquences par vertical : templates éditables dans backend/templates/sequences/<vertical>/ (J0, J+3,
   J+7), en français. Étends services/templating.py : quand le prénom est inconnu, repli sur
   « Bonjour, » (le repli actuel « there » est anglais) sans casser les tests existants.
4. Personnalisation du premier mail avec services/ai_svc.py (repli sur le template sans clé) : le prompt
   ne reçoit que les signaux, le titre et la description du site ; interdiction d'affirmer autre chose.
5. Conformité : chaque mail contient l'identité de l'expéditeur, une phrase sur l'origine des données et un
   lien de désinscription ; en-tête List-Unsubscribe. Endpoint public GET/POST /api/public/unsubscribe/{token}
   (jeton signé HMAC avec JWT_SECRET) qui appelle consent_repo.record_consent(opted_out).
6. Réponses et rebonds : tâche beat toutes les 5 minutes qui lit la boîte IMAP, rapproche par
   In-Reply-To/References, enregistre un outreach_event « replied » (extrait <= 500 caractères dans
   meta, jamais le message complet), détecte les rebonds, et stoppe la séquence du lead en révoquant ses
   tâches Celery en attente (même mécanique que stop_unqualified_sequences).
7. Pixel d'ouverture : GET /api/public/t/{token}.gif => outreach_event « opened ».
8. Prévisualisation : POST /api/campaigns/{id}/preview/{lead_id} renvoie les 3 mails rendus sans envoyer.
Tests : smtplib et imaplib mockés (monkeypatch), aucun appel réseau. Couvre quota, gigue, désinscription,
rapprochement des réponses, arrêt de séquence.
Livrable : tests verts, PR avec une séquence complète rendue pour un prospect fictif.
```

---

## S5 — Dashboard : filtres, score expliqué, Inbox

**Issue** — `[UX] Leads filtrables et expliqués, lancement de séquence en 1 clic, Inbox de suivi`
Livrable : pages branchées sur l'API réelle, aucun état mocké.

```
Mission : issue « Dashboard UX ». Lis CLAUDE.md d'abord. Branche feat/dashboard. S4 est mergée.
Frontend React en JavaScript (pas de TypeScript), composants shadcn/Tailwind existants, design sobre.
- Leads : filtres vertical, ville, signal, score minimum ; colonne score avec une pastille qui ouvre le
  détail par facteur (lead_scores.factors) ; action « Lancer la séquence » en 1 clic (assigne le lead à la
  campagne du vertical et planifie via les endpoints existants).
- Campagnes : envois, ouvertures, réponses, rebonds calculés depuis outreach_events (pas de compteur
  codé en dur).
- Inbox : nouvelle page /app/inbox listant les leads ayant répondu, avec l'historique (envois + extrait
  de la réponse) et trois actions : Relancer (planifie l'étape suivante maintenant), Marquer qualifié,
  Ne plus contacter (opt-out). Un seul ajout backend autorisé : routes/inbox.py (lecture + ces actions)
  avec ses tests d'intégration. Ne modifie pas les autres modules backend.
- Réglages : section « Formulaire inbound » affichant l'URL publique du compte et un extrait HTML copiable
  (champ piège inclus).
Livrable : npm run lint et npm run build verts, test de rendu minimal si un runner existe, PR avec captures
d'écran prises sur l'application tournant avec des données réelles de seed.
```

---

## S6 — Durcissement, E2E, déploiement

**Issue** — `[DEPLOY] Revue sécurité, test E2E du parcours, documentation de déploiement`
Livrable : `docs/deployment.md`, test E2E, limitation de débit, dépendances assainies, pipeline vert.

```
Mission : issue « Revue & déploiement ». Lis CLAUDE.md d'abord. Branche chore/hardening. S1–S5 sont mergées.
1. Relecture senior de tout le code ajouté depuis S1 : secrets, validation des entrées, injection,
   autorisations multi-tenant (un compte ne lit jamais les données d'un autre), doublons, dette. Corrige.
2. Limitation de débit (slowapi + Redis) sur TOUTES les routes publiques : formulaire inbound,
   désinscription, pixel. Tests associés.
3. Dépendances : GitHub signale 65 vulnérabilités sur la branche par défaut (dont 3 critiques). Lance
   pip-audit et npm audit, applique les mises à jour sans changement cassant, liste le reste dans la PR.
4. Test E2E du parcours : fixture de scrape -> signaux -> score -> prévisualisation -> envoi (SMTP mocké)
   -> réponse simulée -> séquence stoppée.
5. docs/deployment.md pas à pas : Render (render.yaml), Netlify pour le frontend, variables d'environnement,
   exécution de alembic upgrade head, vérification du worker et du beat (la planification quotidienne
   repose sur Celery beat, pas sur Vercel Cron), checklist de smoke test, SPF/DKIM/DMARC du domaine d'envoi.
Livrable : CI verte, doc claire, PR de durcissement listant ce qui a été corrigé.
```

---

## Règles d'or

- Une session = une mission = une branche = une PR. Jamais deux missions dans une session.
- Tu relis et merges toi-même ; tu valides les décisions que la session signale dans la PR.
- Session qui part de travers : coupe, garde la PR partielle, relance avec un prompt plus étroit.
- Suis `/usage` pendant chaque session pour calibrer les suivantes.
- Tout doit être mergé et déployé avant le 5 novembre : les crédits non utilisés sont perdus.

## Avant le premier envoi réel

- Domaine d'envoi dédié (pas ton Gmail personnel) avec SPF, DKIM et DMARC configurés.
- Test de bout en bout du lien de désinscription sur un vrai email.
- Identité de l'expéditeur et phrase d'origine des données relues par toi.
- Vérification juridique de la prospection de tes cibles (beaucoup de TPE sont des entrepreneurs individuels).

## Validation business

1. Sourcer 20 à 50 vrais prospects sur UN vertical (ex. restaurants à Marseille).
2. Lancer une seule séquence, 20 mails maximum.
3. Mesurer le taux de réponse. ≥ 10 % : itérer le message. < 5 % : changer de vertical ou de signal avant
   d'ajouter du code.
4. C'est ce chiffre, pas le dashboard, qui décide de la suite.
