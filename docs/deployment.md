# Déploiement

Le détail général (Render, Netlify, CI) est dans le README. Cette page ajoute ce qui concerne OutreachOS.

## Prérequis

1. `alembic upgrade head` (le blueprint `render.yaml` l'exécute en pre-deploy sur le service API : voir « Déployer »). Migrations
   OutreachOS, dans l'ordre : `d4ee9ddac4cf` (découverte), `487fe7f1b98f` (journal d'envoi + limites), `a7c1e9d3b5f2` (statut
   `sending`), `c303c1bc427f` (lots d'import). Chacune est réversible (`alembic downgrade -1`).
2. Variables d'environnement (voir `backend/.env.example`) :

| Variable | Rôle | Obligatoire |
|---|---|---|
| `OUTREACH_SENDER_NAME`, `_COMPANY`, `_ADDRESS`, `_EMAIL` | Identité de l'expéditeur (mentions légales des brouillons) | Pour créer un brouillon |
| `PUBLIC_BASE_URL` | URL publique de l'API (`https://…`), utilisée dans le lien de désinscription | Oui en production |
| `SEND_KILL_SWITCH` | `true` arrête immédiatement tout envoi (dry-run, SendGrid, Twilio) | Non ; à connaître avant d'en avoir besoin |
| `FEATURE_LIVE_SENDING` | `true` autorise l'envoi réel par SMTP (refusé tant que `SMTP_*` est incomplet) | Non, laisser vide |
| `OUTREACH_SANDBOX`, `OUTREACH_LIVE_ALLOWLIST` | Tant que le sandbox est actif (défaut), seule la liste blanche reçoit des e-mails réels | Non |
| `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_SECURITY`, `SMTP_PORT` | Connexion à votre boîte (TLS vérifié obligatoire) | **Oui** : le mot de passe ne va que dans le tableau de bord |
| `FEATURE_PROSPECT_IMPORT` | `true` autorise l'import d'une liste de prospects (CSV/JSON, origine et base légale obligatoires) | Non, laisser vide |
| `AUTH_MAX_FAILURES`, `AUTH_WINDOW_SECONDS`, `REGISTER_MAX_PER_HOUR` | Limitation de débit (voir plus bas) ; défauts 10 / 900 s / 300 | Non |
| `FEATURE_EXTERNAL_SOURCES` | Sources réseau (non implémenté) | Non, laisser vide |
| `TWILIO_AUTH_TOKEN`, `TWILIO_WEBHOOK_URL`, `SENDGRID_WEBHOOK_PUBLIC_KEY` | Vérification des signatures de webhooks | Oui si les webhooks sont utilisés |

3. Le lien de désinscription contient `JWT_SECRET` (clé dérivée) : **changer `JWT_SECRET` invalide tous les liens déjà envoyés**.
   Planifier la rotation en conséquence.

## Avant tout envoi réel (check-list)

L'adaptateur SMTP existe (`services/smtp_svc.py`) ; la procédure pas à pas est dans [`go-live-email.md`](go-live-email.md).
Activer `FEATURE_LIVE_SENDING` sans `SMTP_*` complet est refusé (501). Avant de lever le sandbox, tout ceci doit être vrai, et chaque
point confirmé par une personne :

1. **Configuration explicite** : identité d'expéditeur (`OUTREACH_SENDER_*`), `PUBLIC_BASE_URL` en https, clés du fournisseur
   en variables d'environnement, jamais dans le code.
2. **Domaine d'envoi authentifié** (SPF, DKIM, DMARC) et adresse de réponse relevée ; réputation chauffée progressivement.
3. **Mode sandbox** du fournisseur utilisé d'abord, avec des adresses de test que vous contrôlez.
4. **Limites** réglées volontairement (`/api/outbound/limits`) ; ne pas relever les défauts (20/jour, 60 s) sans raison.
5. **Kill switch testé** en conditions réelles : `SEND_KILL_SWITCH=true` arrête bien tout, et vous savez qui peut redéployer.
6. **Webhooks signés** branchés : rebonds, plaintes, réponses et désinscriptions du fournisseur alimentent `outbound_*` et la
   suppression ; signatures Twilio/SendGrid vérifiées (déjà en place).
7. **Base légale validée** par un juriste (intérêt légitime B2B, entrepreneurs individuels) et registre de traitement tenu.
8. **Tests** : adaptateur testé avec `smtplib` simulé (aucun appel réseau dans la CI), cas d'échec, issue inconnue et reprise couverts ;
   **premier essai réel** = `POST /api/outbound/test-send` vers votre propre adresse, en-têtes SPF/DKIM/DMARC vérifiés.
9. **Confirmation humaine** : une personne nommée active `FEATURE_LIVE_SENDING`, une organisation à la fois.

## Vérifier un déploiement

```bash
curl -s $API/api/health
curl -s -o /dev/null -w '%{http_code}\n' $API/api/unsubscribe/jeton-invalide   # 404 attendu
```
Puis, connecté en `owner` : `POST /api/prospects/discovery/run` → `dry_run: true` ; `GET /api/prospects/settings` →
`dry_run: true`, `live_sending: false`.

## Retour arrière

`git revert` de la PR et `alembic downgrade -1` n'est à faire qu'en dernier recours : il supprime le journal d'envoi (`outbound_*`) et les limites ;
remonter jusqu'à `d4ee…` supprime aussi prospects, scores, brouillons et suppressions (donc les opt-out enregistrés).
Sauvegarder avant.

## Local

Voir le README (« Parcours local OutreachOS »).


## Déployer (Render pour l'API, Netlify pour l'interface)

1. **API** : le blueprint `render.yaml` crée `clawpilot-api` (web), `clawpilot-worker` et `clawpilot-beat` (Celery), la base Postgres et
   Redis. Les noms gardent l'ancien préfixe `clawpilot-` volontairement : les renommer créerait de nouveaux services et une base vide.
   Les secrets (`sync: false`) se saisissent dans le tableau de bord, jamais dans le dépôt.
2. **Migrations** : `preDeployCommand: alembic upgrade head` s'exécute avant que la nouvelle version prenne le trafic ; en cas d'échec,
   Render garde l'ancienne version. Vérifier dans les logs du déploiement la ligne `Running upgrade … -> …`.
3. **Déclenchement** : à chaque push sur `main`, la CI appelle `RENDER_DEPLOY_HOOK_URL` (secret GitHub) si défini ; sinon *Manual Deploy*.
4. **Interface** : Netlify construit `frontend/` (`netlify.toml`) avec `REACT_APP_BACKEND_URL` = URL publique de l'API ; `CORS_ORIGINS` de
   l'API doit contenir l'URL de l'interface. En-têtes de sécurité posés par `netlify.toml` (cadres refusés, `nosniff`, HSTS, politique de
   référent, permissions).
5. Vercel n'est pas utilisé ; le même `npm run build` (dossier `build/`, repli SPA vers `index.html`) y fonctionnerait.

## Tâches planifiées (cron quotidien)

Le service `clawpilot-beat` (`celery -A celery_app beat`) pilote les tâches périodiques déclarées dans `backend/celery_app.py` ; le
worker (`-Q sends,automation,webhooks`) les exécute. Quotidiennes, en UTC : 03:00 re-scoring des leads actifs, 04:00 arrêt des séquences
non qualifiées, 05:00 réactivation des leads dormants ; toutes les 30 s : reprise des envois planifiés perdus. **Ne jamais lancer deux
`beat`** : chaque tâche partirait deux fois. Toute tâche d'envoi passe par `send_gate` (pause, limites, kill switch).

## Limitation de débit

Connexion : 10 échecs par adresse e-mail et par 15 minutes, puis `429` avec `Retry-After` (même le bon mot de passe n'est pas confirmé
pendant le blocage). Inscription : 300 par heure au total. Limites en mémoire, par processus : plusieurs instances multiplient la limite
et un redémarrage la remet à zéro ; passer à Redis si l'API est répliquée. Les envois ont leurs propres plafonds (`/api/outbound/limits`).

## Vérifier avant de livrer

```bash
cd backend && pytest tests/ -q                  # 387 tests, serveur démarré (voir ci.yml)
cd frontend && npm test -- --watchAll=false && npm run lint && npm run build
cd frontend && npm run e2e                       # parcours complet via l'interface, API réelle
```
Lighthouse (mesuré en local sur le build : accueil/connexion/inscription/mentions légales) : performance 93–96, accessibilité 100,
bonnes pratiques 96 (les 4 points manquants viennent du chargement de polices bloqué par le bac à sable de test), SEO 100. Les pages
connectées n'ont pas été mesurées.

## Revue de sécurité (état)

Fait : secrets hors dépôt et hors logs (scan GitGuardian en CI) ; webhooks signés et fermés en production ; envoi réel derrière quatre
verrous (`SMTP_*`, `FEATURE_LIVE_SENDING`, liste blanche, kill switch) ; import borné et attesté ; limitation de débit ; en-têtes ;
CORS restreint aux origines déclarées. Connu et accepté : le jeton de session est dans le stockage local du navigateur (exposé en cas de
faille XSS) ; `passlib` n'est plus maintenu ; limites de débit en mémoire. À faire : suivi IMAP/webhook des réponses et rebonds réels,
pied de message et désinscription sur les anciens chemins d'envoi (Messages, lots, campagnes), enrichissement des sites derrière
`FEATURE_EXTERNAL_SOURCES`.
