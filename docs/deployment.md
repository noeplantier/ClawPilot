# Déploiement

Le détail général (Render, Netlify, CI) est dans le README. Cette page ajoute ce qui concerne OutreachOS.

## Prérequis

1. `alembic upgrade head` (le blueprint `render.yaml` l'exécute en pre-deploy). Cette tranche ajoute la migration
   `d4ee9ddac4cf` (découverte) puis `487fe7f1b98f` (journal d'envoi + limites) ; elle est réversible (`alembic downgrade -1`).
2. Variables d'environnement (voir `backend/.env.example`) :

| Variable | Rôle | Obligatoire |
|---|---|---|
| `OUTREACH_SENDER_NAME`, `_COMPANY`, `_ADDRESS`, `_EMAIL` | Identité de l'expéditeur (mentions légales des brouillons) | Pour créer un brouillon |
| `PUBLIC_BASE_URL` | URL publique de l'API (`https://…`), utilisée dans le lien de désinscription | Oui en production |
| `SEND_KILL_SWITCH` | `true` arrête immédiatement tout envoi (dry-run, SendGrid, Twilio) | Non ; à connaître avant d'en avoir besoin |
| `FEATURE_LIVE_SENDING` | `true` autorise l'envoi réel (aucun adapter n'existe encore) | Non, laisser vide |
| `FEATURE_EXTERNAL_SOURCES` | Sources réseau (non implémenté) | Non, laisser vide |
| `TWILIO_AUTH_TOKEN`, `TWILIO_WEBHOOK_URL`, `SENDGRID_WEBHOOK_PUBLIC_KEY` | Vérification des signatures de webhooks | Oui si les webhooks sont utilisés |

3. Le lien de désinscription contient `JWT_SECRET` (clé dérivée) : **changer `JWT_SECRET` invalide tous les liens déjà envoyés**.
   Planifier la rotation en conséquence.

## Avant tout envoi réel (check-list)

Aucun adaptateur réel n'existe ; activer `FEATURE_LIVE_SENDING` aujourd'hui est refusé (501). Avant d'en écrire un, tout ceci doit
être vrai, et chaque point confirmé par une personne :

1. **Configuration explicite** : identité d'expéditeur (`OUTREACH_SENDER_*`), `PUBLIC_BASE_URL` en https, clés du fournisseur
   en variables d'environnement, jamais dans le code.
2. **Domaine d'envoi authentifié** (SPF, DKIM, DMARC) et adresse de réponse relevée ; réputation chauffée progressivement.
3. **Mode sandbox** du fournisseur utilisé d'abord, avec des adresses de test que vous contrôlez.
4. **Limites** réglées volontairement (`/api/outbound/limits`) ; ne pas relever les défauts (20/jour, 60 s) sans raison.
5. **Kill switch testé** en conditions réelles : `SEND_KILL_SWITCH=true` arrête bien tout, et vous savez qui peut redéployer.
6. **Webhooks signés** branchés : rebonds, plaintes, réponses et désinscriptions du fournisseur alimentent `outbound_*` et la
   suppression ; signatures Twilio/SendGrid vérifiées (déjà en place).
7. **Base légale validée** par un juriste (intérêt légitime B2B, entrepreneurs individuels) et registre de traitement tenu.
8. **Tests** : adaptateur testé avec le fournisseur simulé (aucun appel réseau dans la CI), cas d'échec et reprise couverts.
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
