# Déploiement

Le détail général (Render, Netlify, CI) est dans le README. Cette page ajoute ce qui concerne OutreachOS.

## Prérequis

1. `alembic upgrade head` (le blueprint `render.yaml` l'exécute en pre-deploy). Cette tranche ajoute la migration
   `d4ee9ddac4cf` (nouvelles tables + colonnes de `leads`) ; elle est réversible (`alembic downgrade -1`).
2. Variables d'environnement (voir `backend/.env.example`) :

| Variable | Rôle | Obligatoire |
|---|---|---|
| `OUTREACH_SENDER_NAME`, `_COMPANY`, `_ADDRESS`, `_EMAIL` | Identité de l'expéditeur (mentions légales des brouillons) | Pour créer un brouillon |
| `PUBLIC_BASE_URL` | URL publique de l'API (`https://…`), utilisée dans le lien de désinscription | Oui en production |
| `FEATURE_LIVE_SENDING` | `true` autorise l'envoi réel (aucun adapter n'existe encore) | Non, laisser vide |
| `FEATURE_EXTERNAL_SOURCES` | Sources réseau (non implémenté) | Non, laisser vide |
| `TWILIO_AUTH_TOKEN`, `TWILIO_WEBHOOK_URL`, `SENDGRID_WEBHOOK_PUBLIC_KEY` | Vérification des signatures de webhooks | Oui si les webhooks sont utilisés |

3. Le lien de désinscription contient `JWT_SECRET` (clé dérivée) : **changer `JWT_SECRET` invalide tous les liens déjà envoyés**.
   Planifier la rotation en conséquence.

## Vérifier un déploiement

```bash
curl -s $API/api/health
curl -s -o /dev/null -w '%{http_code}\n' $API/api/unsubscribe/jeton-invalide   # 404 attendu
```
Puis, connecté en `owner` : `POST /api/prospects/discovery/run` → `dry_run: true` ; `GET /api/prospects/settings` →
`dry_run: true`, `live_sending: false`.

## Retour arrière

`git revert` de la PR et `alembic downgrade d4ee…` n'est à faire qu'en dernier recours : le downgrade supprime les tables de
prospects, scores, brouillons et suppressions (donc les opt-out enregistrés). Sauvegarder avant.

## Local

Voir le README (« Parcours local OutreachOS »).
