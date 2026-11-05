# Campagne individuelle : 100 e-mails personnalisés, relus et planifiés

Cet écran (**Outreach › Campagne individuelle**, `/app/launch`) prépare et suit une campagne où **chaque destinataire reçoit son
propre message**, écrit pour lui, relu par une personne, planifié puis envoyé un par un. Il ne recrée aucun moteur : les brouillons
viennent du flux IA existant (`services/draft_runner.py`), chaque message part par l'unique `dispatch_draft`
(`services/outreach_os/dispatch.py`), les limites et la pause sont celles de `services/send_gate.py`. Ce document dit ce qui est
ajouté, ce qui est vérifié à chaque étape et **ce que fait chaque bouton**.

**Rien ne part pendant la préparation.** Sélectionner, générer, approuver et planifier n'écrivent que des brouillons et des lignes de
plan. Un message ne quitte le serveur que si l'envoi réel est activé (`FEATURE_LIVE_SENDING=true`), que le fournisseur est complet,
que le bac à sable le permet, qu'un worker et le beat tournent, et que toutes les portes ci-dessous sont ouvertes **au moment de son
envoi**.

## Le parcours en six étapes

| # | Étape | Ce qui est fait | Ce qui est écrit |
|---|---|---|---|
| 1 | Fournisseur et garde-fous | Lecture seule : fournisseur actif, ce qu'il interdit, limites, fenêtre, mode (simulation / réel), bac à sable, arrêt d'urgence, pause, worker | Rien |
| 2 | Sélection | Jusqu'à 100 établissements **distincts**, les mieux classés d'abord (intention commerciale observée, puis chaleur) | Une campagne `kind = individual`, statut `draft`, et la liste de ses destinataires |
| 3 | Brouillons | Un brouillon IA par destinataire qui n'en a pas (bouton), en arrière-plan | Des brouillons au statut `draft` (jamais approuvés) |
| 4 | Revue | Destinataire, objet, corps, preuves utilisées, autorisation du canal, erreurs ; approbation ou rejet | Le statut du brouillon (`approved` / `rejected`) |
| 5 | Plan | Nombre réellement envoyable, exclusions, calendrier ; bouton **Planifier les messages approuvés** | Une ligne `campaign_dispatches` par message, avec son heure au plus tôt ; la campagne passe `running` |
| 6 | Suivi | État honnête de chaque destinataire | Rien |

### 1. Fournisseur actif et ce qu'il autorise

Le fournisseur est celui qui porterait un vrai message (`SMTP_HOST`, sinon SendGrid), **que l'envoi réel soit activé ou non** : une
répétition en simulation exclut les mêmes destinataires que l'envoi réel. L'écran n'affiche que des noms et des nombres, jamais une
valeur de secret (`services/outreach_os/provider_policy.py`).

| Fournisseur | Politique | Conséquence |
|---|---|---|
| **Hostinger** (`*hostinger*`, `titan.email`) | `opt_in_required` : ses conditions interdisent l'envoi en masse non sollicité | Seuls les destinataires avec un **opt-in explicite** (consentement e-mail `opted_in`) ou issus d'une **base importée déclarée « consentement »** reçoivent une campagne. Un contact trouvé dans un annuaire public, sans opt-in, est **exclu** (`provider_requires_opt_in`) |
| Autre SMTP, SendGrid | `unverified` : l'application ne connaît pas ses conditions | Rien n'est bloqué sur une supposition ; l'écran demande de relire les conditions avant tout envoi réel |
| Aucun | `not_configured` | Seule la simulation est possible |

**Un quota d'envoi disponible ne vaut pas autorisation.** Les limites (jour, heure, délai) bornent un débit ; elles ne disent pas
qu'un destinataire a le droit de recevoir cette campagne par ce fournisseur. Les deux sont vérifiés, séparément.

Base de l'autorisation, de la plus forte à « rien d'enregistré » : `opt_in` › `declared_consent` › `legitimate_interest_b2b`
(base déclarée à l'import, pas un opt-in) › `public_directory`. La base légale d'une liste importée est lue dans la note de licence de
sa source (`legal basis: consent`).

### 2. Sélection : 100 établissements distincts

Sont candidats les prospects **validés par une personne** et **qualifiés** (même politique d'éligibilité que la carte,
`docs/eligibility.md`). Chaque prospect écarté garde sa raison, affichée à l'écran :

| Code | Raison |
|---|---|
| `not_approved`, `rejected` | Pas validé / rejeté par une personne |
| `demo` | Donnée de démonstration confirmée |
| `suppressed`, `opted_out` | Liste de suppression, désinscription ou opposition |
| `not_qualified`, `no_email`, `invalid_email` | Incomplet (voir *À enrichir*) ou adresse absente / factice |
| `bounced` | Rebond bloquant sur cette adresse |
| `already_replied` | A déjà répondu |
| `already_contacted` | A déjà reçu un message (envoyé, en cours, répondu ou rebondi ; un échec ne compte pas) |
| `campaign_conflict` | Déjà dans une autre campagne en cours ou un autre lot individuel |
| `provider_requires_opt_in` | Le fournisseur actif exige un opt-in que ce contact n'a pas |
| `duplicate_email` | Même adresse déjà retenue (adresse normalisée) |
| `duplicate_establishment` | Même nom (casse et accents ignorés) dans la même ville déjà retenu |

« **Compléter la sélection jusqu'à 100** » ajoute de nouveaux établissements distincts sans toucher à ceux déjà retenus.

### 3. Brouillons individuels (IA existante)

Le bouton **Générer les brouillons manquants** lance, **en arrière-plan et uniquement pour les destinataires de la campagne**, la même
préparation que celle des brouillons automatiques : même offre (`Pilotage › Offre`), mêmes contrôles de sécurité, même cache.

- Le brouillon est écrit à partir du nom, de l'activité, de la ville, du site et des **constats sourcés** (signaux au statut
  `detected`). Un fait non porté par un signal n'est jamais affirmé ; un doute fait **rejeter** la proposition (`draft_rejected`).
- **Cache et idempotence** : la clé d'un brouillon combine compte, prospect, offre, version du gabarit et empreinte des données. Les
  mêmes données ne régénèrent rien ; un brouillon validé ou modifié à la main n'est jamais écrasé.
- **Rien n'est généré au rendu d'un composant** : l'écran ne fait que lire. Sans offre décrite, le bouton répond `409`
  (« Décrivez d'abord votre offre ») plutôt que d'inventer un texte.
- Trois états du site, jamais déduits d'un champ vide : **Site présent** · **Aucun site identifié après recherche** (affirmé
  seulement si l'annuaire a été lu et n'en portait pas) · **Site inconnu**. Un champ vide seul reste « inconnu ».

### 4. Revue avant lancement

Pour chaque destinataire : adresse, objet, corps (dépliable), **preuves utilisées** (constats, état du site, source et date de relevé),
**autorisation du canal** (avec sa base : opt-in, consentement déclaré, intérêt légitime, annuaire public), brouillon manquant ou rejeté,
et les **points bloquants** :

| Point | Bloquant ? |
|---|---|
| Objet ou corps vide | Oui |
| **Variable non résolue** (`{{x}}`, `{x}`, `%X%`, `[[x]]`, `<<x>>`, `[Ville]`…) | Oui |
| **Constat sans source actuelle** (signal écarté ou plus observé depuis la rédaction) | Oui |
| Identité de l'expéditeur absente, ou pied de message non conforme (identité, adresse postale, origine des données, lien de désinscription) | Oui |
| Texte modifié à la main | Non : « à savoir », les affirmations ajoutées ne sont pas vérifiées |

Un brouillon bloquant ne peut pas être approuvé (l'interface le grise **et** le serveur le refuse). Un brouillon approuvé dont une preuve
disparaît ensuite passe à **Bloqués** et sort du plan.

### 5. « Planifier les messages approuvés »

Le plan est **calculé par le serveur à l'instant** à partir des données, jamais depuis ce qu'un écran affichait : nombre réellement
envoyable, exclusions par raison, premier et dernier envoi, jours. Le bouton envoie le nombre lu (`expected_count`) : s'il a changé,
**rien n'est écrit** (`409 plan_changed`) et le plan est relu.

- **Un message par destinataire**, un seul `To`, **jamais de `Cc` ni de `Bcc`** collectif, un lien de désinscription propre à chacun.
- Chaque message reçoit une heure « au plus tôt » respectant la fenêtre d'envoi (lue dans le fuseau du destinataire quand la politique
  l'indique), le plafond quotidien (jours de l'organisation), le plafond horaire glissant et le délai minimal, en comptant ce qui est déjà
  parti par tous les chemins. Avec la politique par défaut (20 par jour, 60 s) : **100 messages ≈ 5 jours d'envoi** (aucun jour de repos n'est supposé : le calendrier ne connaît que la fenêtre horaire).
- Ce sont des heures « pas avant » : à l'envoi réel, **les mêmes limites sont relues** contre ce qui s'est vraiment passé.
- **Annuler les messages non partis** annule les lignes encore planifiées et met la campagne en pause. Ce qui est déjà parti ne se rappelle pas.

### 6. Portes d'envoi, revérifiées au moment effectif de chaque message

Le planificateur (`tasks.campaign_tasks.process_due_dispatches`, toutes les 60 s sur la file `sends`) prend chaque message dû (réservation
atomique : deux workers ne peuvent pas envoyer le même), repasse **toutes** les portes, puis passe par `dispatch_draft` :

| Porte | Refus « attendre » (le message est replanifié) | Refus « arrêter » (le message ne part pas) |
|---|---|---|
| Arrêt d'urgence `SEND_KILL_SWITCH`, pause de l'organisation, campagne en pause | ✔ (prochaine vérification 15 min plus tard) | |
| Limite quotidienne, horaire, délai minimal | ✔ (à l'heure où la limite se libère) | |
| Fenêtre d'envoi du destinataire | ✔ (à l'ouverture suivante) | |
| Envoi réel activé sans SMTP complet, identité d'expéditeur manquante | ✔ | |
| Brouillon plus approuvé, prospect plus validé / supprimé, adresse changée depuis le plan | | ✔ |
| **Suppression**, désinscription / **opposition**, rebond | | ✔ |
| **Réponse** déjà reçue, prospect passé dans une autre campagne | | ✔ |
| Fournisseur qui exige un opt-in que le contact n'a pas | | ✔ |
| **Bac à sable** : destinataire absent de `OUTREACH_LIVE_ALLOWLIST` | | ✔ |
| Contenu non conforme (identité, origine, désinscription) | | ✔ |

Un refus « attendre » ne perd jamais un message et ne le marque jamais en échec. Un refus à l'échelle du compte (arrêt d'urgence, pause,
limite) arrête le tour pour ce compte et laisse les autres messages à leur heure.

**Aucun renvoi aveugle.** La ligne `sending` est validée **avant** l'appel du fournisseur (au plus une fois). Un résultat ambigu
(connexion perdue après `DATA`, exception de l'adaptateur) devient **« Résultat inconnu »** et n'est **jamais renvoyé** : une personne
vérifie la boîte d'envoi. Un message resté `sending` après une interruption est réglé **depuis le registre d'envoi** (message trouvé →
accepté / échec / inconnu ; aucune trace → replanifié), jamais renvoyé à l'aveugle.

### 7. Suivi honnête

| État | Sens |
|---|---|
| Planifié | Un créneau est réservé, rien n'est parti |
| En cours d'envoi | Pris par un worker |
| **Accepté par SMTP** | Le serveur d'envoi a pris le message. **Ce n'est pas une preuve de livraison** |
| Simulé | Envoi réel désactivé (dry-run) : rien n'est parti |
| Réponse reçue · Opposition · Rebond | Observés par la boîte de réception / les webhooks |
| Échec | Refusé de façon définitive par le serveur |
| Résultat inconnu | Jamais renvoyé : à vérifier dans la boîte d'envoi |
| Arrêté (raison) · Annulé | Parti d'aucune manière : la raison est affichée |

**« Livré » n'existe pas** : rien dans le système n'observe une livraison, donc aucun message n'est jamais marqué ainsi.

## Actions exactes dans l'interface

1. **Pilotage › Offre** : décrivez ce que vous vendez (obligatoire pour les brouillons IA).
2. **Leads › À vérifier** : validez (ou rejetez) les prospects. Seuls les validés sont candidats.
3. **Outreach › Campagne individuelle** : relisez le panneau *1 · Fournisseur et garde-fous* (fournisseur, restriction, simulation ou réel,
   bac à sable, limites, worker et beat détectés).
4. *2 · Sélectionner les établissements* : nom, nombre (100) puis **Sélectionner 100 établissements**. Lisez les exclusions par raison ;
   **Compléter la sélection jusqu'à 100** si besoin.
5. *3 · Brouillons individuels* : **Générer les brouillons manquants (N)**, attendez la fin (la liste se rafraîchit seule).
6. *4 · Revue avant lancement* : onglet **À relire**, ouvrez objet et corps, vérifiez preuves et autorisation, cochez les brouillons
   propres (**Tout sélectionner**), **Approuver la sélection**. Corrigez un brouillon dans la fiche du prospect si besoin.
7. *5 · Plan d'envoi* : relisez le nombre réellement envoyable, les exclusions et le calendrier, puis **Planifier les messages
   approuvés** → **Confirmer : planifier N**. *Aucun message ne part à cet instant.*
8. *6 · Suivi* : suivez les états. **Annuler les messages non partis** arrête tout ce qui n'est pas encore parti.

L'envoi **réel** reste une décision distincte, hors de cet écran : `FEATURE_LIVE_SENDING=true`, `OUTREACH_SANDBOX=false` et le
fournisseur complet, comme décrit dans `docs/go-live-email.md`. Tant que ce n'est pas fait, les messages sont **simulés**.

## Prérequis d'exécution

Le plan n'est exécuté que si **un worker Celery et son beat tournent** (`celery -A celery_app worker -Q sends,automation,webhooks`
et `celery -A celery_app beat`). Sur l'offre gratuite sans service worker, `EMBEDDED_WORKER=1` les lance dans le conteneur de l'API
(`docs/deployment.md`). L'écran lit `/api/launches/provider` et dit si un worker et le beat sont détectés ; sans eux, le plan reste
écrit mais rien ne part.

## API (`/api/launches`, rôles `owner`/`admin` pour écrire)

`GET /provider` · `GET ` · `POST ` (création) · `POST /{id}/top-up` · `GET /{id}` · `POST /{id}/drafts` (202) · `GET /{id}/review` ·
`POST /{id}/review-drafts` · `GET /{id}/plan` · `POST /{id}/schedule` · `POST /{id}/cancel` · `GET /{id}/tracking`.

Les routes d'envoi des séquences (`assign-leads`, `run-step`, `launch`, `schedule`) **refusent** une campagne individuelle (`409`) : ses
messages ne partent que par ce parcours.

## Données

Table `campaign_dispatches` (migration `20261105_01`) : une ligne par destinataire et par campagne (`uq_campaign_dispatches_campaign_lead`),
au plus **un message actif** (`scheduled`/`sending`) par prospect et par compte (`uq_campaign_dispatches_active_lead`, index partiel),
statuts `scheduled · sending · accepted · failed · unknown · skipped · cancelled`, clé d'idempotence d'envoi `campaign:{id}`. RLS activée
(tout le schéma `public` est exposé par l'API de données de Supabase). `campaigns.kind` : `sequence` (défaut) ou `individual`.

## Tests

- `backend/tests/unit/test_campaign_plan.py`, `test_provider_policy.py` : règles pures (exclusions, variables, constats, calendrier,
  suivi, politique du fournisseur), sans serveur ni réseau.
- `backend/tests/test_campaign_launch.py` : le parcours complet sur la vraie base, avec un adaptateur qui **enregistre** (aucun
  transport réel, aucune base de production) : 100 destinataires → 100 messages distincts, personnalisation, absence de `Cc`/`Bcc`,
  déduplication, idempotence, arrêt après réponse / opposition / suppression, limites, fenêtre, arrêt d'urgence, pause, bac à sable,
  Hostinger, résultat ambigu jamais renvoyé, reprise après interruption, isolation entre comptes.
- `frontend/src/lib/launchFormat.test.js`, `frontend/src/pages/launch.test.jsx` : formatage pur et rendu de l'écran (API simulée).

## Limites connues

- Le suivi des réponses et des oppositions dépend de la synchronisation de la boîte de réception et des webhooks du fournisseur ; sans
  elle, l'état reste « accepté » (jamais « livré »).
- La fenêtre d'envoi se lit dans le fuseau du pays du prospect quand la politique est `lead_country` ; un prospect sans pays utilise le
  fuseau de l'organisation.
- `docs/schema.md` n'est pas régénéré par cette fonctionnalité : `cd backend && python -m scripts.gen_schema_doc`.
