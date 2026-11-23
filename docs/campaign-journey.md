# Campagne par zone : zone → brouillon → approbation

Écran : **Outreach › Campagne par zone** (`/app/journey`). Trois décisions seulement, le système fait le reste :

1. **La zone** : le rectangle réellement cherché sur la carte (bouton « Continuer vers la campagne » du panneau Prospection).
2. **Le brouillon** : un modèle de message prérempli depuis l'offre configurée, modifiable, avec quelques exemples rendus sur de
   vrais établissements de la zone.
3. **L'approbation** : une synthèse (audience, exclusions, version du message, volume, expéditeur, calendrier) puis une confirmation.
   L'approbation lance **cette** campagne, pas un envoi illimité.

Rien n'est recréé : le parcours s'appuie sur la campagne individuelle (`campaign_dispatches`, `campaign_launch.process_due`) et sur
l'unique `dispatch_draft`. Il ajoute une zone, un modèle contrôlé, une approbation liée au contenu et une porte de plus à l'envoi.
Voir `docs/campaign-launch.md` pour le moteur d'envoi et `docs/automation-max.md` pour le mode automatique borné.

**Approuver n'envoie rien tout de suite.** Cela écrit un brouillon par destinataire et un plan ; chaque message est envoyé plus tard
par la tâche planifiée (`tasks/campaign_tasks.py`), qui revérifie **toutes** les portes au moment de l'envoi.

## Ce que fait chaque écran

| Écran | Appel | Écrit |
|---|---|---|
| Panneau Prospection (carte) | recherche existante | des places trouvées, rien d'envoyé |
| Configuration en une fois | `GET /api/journeys/readiness` | rien |
| Créer la campagne | `POST /api/journeys` | une campagne `individual` avec sa zone, la sélection, un premier modèle (version 1) |
| Écran d'approbation | `GET /api/journeys/{id}` | rien (tout est recalculé à la lecture) |
| Enregistrer le message | `PUT /api/journeys/{id}/template` | une nouvelle version si le texte change (un changement d'espaces n'en est pas un) |
| Approuver | `POST /api/journeys/{id}/approve` | l'approbation, un brouillon par destinataire, le plan |
| Retirer l'approbation | `POST /api/journeys/{id}/revoke` | l'approbation retirée, les envois planifiés annulés, campagne en pause |
| Pause / reprise | `POST /api/journeys/{id}/pause`, `/resume` | le statut ; la reprise est refusée si l'approbation ne couvre plus la campagne |
| Suivi | `GET /api/journeys/{id}/progress` | rien |

Lire est ouvert à tout membre ; créer, éditer, approuver, retirer et mettre en pause demandent un propriétaire ou un administrateur.

## La zone et ce qui est vraiment couvert

La zone est un rectangle (sud, ouest, nord, est) et une catégorie, validés par le serveur (coordonnées cohérentes, pas plus de
`ZONE_MAX_SPAN` degrés). Le panneau de la carte affiche le **périmètre réellement recherché** (coordonnées et taille) et ne propose le
passage à la campagne qu'après une recherche réussie.

L'écran ne promet jamais « tous les établissements » : il affiche le nombre trouvé par la dernière recherche qui couvre la zone, sa
date, et si la recherche a atteint son plafond (`truncated`) ; sans recherche terminée, il le dit. Aucune source n'est exhaustive.

## Configuration en une fois

`readiness` renvoie une courte liste : offre décrite, identité d'expéditeur, fournisseur (bloquants, chacun avec la correction exacte et
le lien), puis réponses lues (IMAP), worker et planificateur, mode d'envoi (informatifs, ne bloquent pas). Une fois tout en place, la
liste se replie en une ligne. Un point manquant désactive « Approuver » et dit pourquoi ; rien n'est simulé pour passer.

## Le modèle de message

Modèle commun, rendu **par établissement** par le serveur (`services/outreach_os/campaign_template.py`, pur, sans I/O). Champs de
fusion : `{{nom}}` (obligatoire : un message qui ne nomme pas l'établissement est un envoi de masse, refusé), `{{activite}}`,
`{{ville}}`, `{{constat}}`, `{{offre}}`, `{{pitch}}`, `{{cta}}`, `{{expediteur}}`.

- `{{constat}}` n'affirme que des faits portés par un signal `detected`. Selon l'état du site : site connu, site injoignable à la dernière
  vérification, aucun site identifié après recherche (formulation prudente : « sauf erreur de ma part… »), ou inconnu (aucune phrase
  sur le site). `unknown` n'est jamais traité comme « pas de site ».
- Les textes venus de sources externes (nom, adresse, descriptions) sont des **données non fiables** : tronqués, jamais exécutés ni
  interprétés comme des instructions.
- Un champ vide pour un établissement le **retient** (liste « Retenus », avec la raison) au lieu d'inventer une valeur.
- Le pied du message (identité de l'expéditeur, origine des données, lien de désinscription) est ajouté par le serveur à chaque message,
  construit pour chaque destinataire ; il n'est pas modifiable.
- Pas d'IA au rendu : le modèle est contrôlé et déterministe. Il n'y a pas 500 variantes générées ; une suggestion IA du modèle reste une
  extension possible (budget, cache, concurrence bornée), **non branchée** ici.

## L'approbation est liée à ce qui est approuvé

L'approbation enregistre quatre empreintes : le contenu du modèle (espaces normalisés), la zone (rectangle arrondi + catégorie),
l'offre et l'empreinte de l'expéditeur, ainsi que les plafonds. Elle devient **périmée** (`approval_stale`, visible dans l'écran et le
suivi) quand l'une change : `template_changed`, `zone_changed`, `offer_changed`, `sender_changed`, ou quand elle est retirée
(`revoked`) ou expirée (`expired`). Modifier le message crée une nouvelle version : les modifications de l'utilisateur sont conservées,
l'ancienne approbation ne couvre simplement plus la nouvelle version.

L'approbation envoie le hash du contenu lu et le nombre de messages affichés. Si le message ou ce nombre ont changé depuis la lecture
de l'écran, le serveur répond 409 sans rien écrire et l'écran se recharge.

## À chaque envoi (porte supplémentaire)

`services/journey_gate.py`, appelé par `campaign_launch.process_due` avant `dispatch_draft`, refuse le message si : l'approbation est
absente, périmée, retirée ou expirée ; la campagne est en pause ; le brouillon n'est pas de la version approuvée ; le plafond du jour ou le
plafond total est atteint. La ligne en cours d'envoi est exclue de son propre décompte. Ces refus s'ajoutent à toutes les portes
existantes (arrêt d'urgence, pause du compte, limites, consentement, désinscription, bac à sable, liste blanche) : aucune n'est retirée.

Un destinataire par message, jamais de copie collective. Une réponse, une opposition ou un rebond bloquant arrête les envois suivants
à cette personne ; un même établissement n'est pas contacté deux fois entre campagnes ; un résultat ambigu du fournisseur n'est **jamais**
renvoyé automatiquement et reste visible (« résultat inconnu »).

## États affichés (honnêtes)

Planifié · en cours d'envoi · accepté par le serveur SMTP · simulé (rien n'est parti) · réponse · opposition · rebond · refusé · résultat
inconnu · écarté au moment de l'envoi · annulé. « **Livré** » n'existe pas : un serveur SMTP qui accepte un message n'est pas une preuve
de réception. Le tableau principal ne montre que : progression, action requise, réponses, pause et reprise.

## Le flux d'e-mail (cause et correctifs)

Diagnostiqué dans le code et par des tests isolés (aucun transport réel) :

- **Envoi sans SendGrid** : SMTP suffit ; `mail_provider.send_email` choisit SMTP si la configuration est complète et que `dry_run` est
  faux, sinon SendGrid, sinon refuse en disant quoi configurer. SendGrid n'est jamais exigé, Twilio ne bloque pas l'e-mail.
- **Pas de renvoi aveugle** : la tâche d'envoi écrit une ligne `queued` validée avant d'appeler le fournisseur ; un nouvel essai qui
  trouve cette ligne renvoie `skipped / already_attempted`. Un résultat ambigu est marqué et n'est jamais retenté.
- **Liste blanche** : elle ne restreint que lorsque le bac à sable est actif ; hors bac à sable elle est sans effet et l'aperçu de campagne
  le dit (`sandbox.scope`).
- **Dérive worker/API** : l'API et le worker lisent chacun leur propre environnement. Le worker publie l'empreinte de sa
  configuration d'envoi (booléens, noms et compteurs, jamais une valeur : envoi réel, bac à sable, arrêt d'urgence, fournisseur,
  hôte SMTP, identité, taille de la liste blanche) et l'API la compare à la sienne (`services/runtime_config.py`,
  `services/celery_health.py`) : un écran « prêt » alors que le worker refuserait, ou l'inverse, devient visible.
- **Diagnostic à la demande** : `POST /api/settings/email/diagnostics` (`services/mail_diagnostics.py`) ne tourne jamais tout seul : un
  propriétaire ou un administrateur le demande explicitement. Il vérifie la résolution du nom, la cohérence port / sécurité, le certificat TLS, la connexion
  SMTP (**arrêtée avant `MAIL FROM`** : aucun message n'est envoyé), le dossier IMAP en lecture seule, et les enregistrements DNS du
  domaine expéditeur (SPF, indice DKIM, DMARC : des prérequis, pas une garantie de réception). Aucun identifiant, adresse ou nom
  d'utilisateur n'apparaît dans un résultat ou un journal. Un diagnostic sur des identifiants de production reste une action à
  décider par le propriétaire.
- **Réponses** : le worker note l'heure de chaque relève réussie de la boîte (`tasks/inbox_tasks.py`, `services/inbox_health.py`) ;
  sans relève depuis 20 minutes, les réponses sont considérées comme non lues et le mode automatique refuse d'agir.

## Vérifier localement

```bash
cd backend && pytest tests/unit/test_campaign_template.py tests/unit/test_email_flow.py tests/unit/test_mail_diagnostics.py
uvicorn server:app --port 8000 &
REACT_APP_BACKEND_URL=http://localhost:8000 pytest tests/test_journey.py tests/test_email_diagnostics.py -v
cd ../frontend && npm test -- --watchAll=false src/pages/journey.test.jsx src/lib/journeyFormat.test.js
```

Aucun de ces tests n'envoie de message : le transport est le puits de test (`OUTREACH_TEST_SINK`) ou une simulation.

## Limites connues

- Une zone = un rectangle ; la recherche est celle de la carte (OpenStreetMap), pas une découverte automatique dans le parcours.
- Au plus 100 messages par campagne (le plafond du moteur de campagne individuelle).
- Le modèle est contrôlé ; aucune génération IA n'est faite par ce parcours.
- Les conditions du fournisseur (par exemple Hostinger, qui interdit l'envoi de masse non sollicité) et le droit applicable restent
  **deux vérifications distinctes, faites par une personne** : l'application les rappelle, elle ne les remplace pas.
