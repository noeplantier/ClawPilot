# Envoi réel depuis `founder@plantiers.com` (SMTP)

Ce document décrit comment faire sortir un vrai e-mail de Plantiers - OutreachOS **depuis votre boîte**, et ce que cela ne couvre pas encore.
Par défaut rien ne sort : `FEATURE_LIVE_SENDING` est éteint, l'adaptateur est un simulateur (dry-run).

## Ce qui est branché

| Chemin | Fournisseur | État |
|---|---|---|
| Brouillons de prospects approuvés (`POST /api/outbound/dispatch`) | **SMTP** (`services/smtp_svc.py`) quand `FEATURE_LIVE_SENDING=true`, sinon dry-run | Identité, origine des données, lien de désinscription et en-têtes `List-Unsubscribe` dans chaque message |
| Test de connexion (`POST /api/outbound/test-send`) | SMTP | Un seul message technique, uniquement vers **votre propre adresse** ou une adresse de la liste blanche |
| Page *Messages*, lots, campagnes (anciens chemins) | **SendGrid** ou mock, **pas** SMTP | Voir « Limites connues » |

## Variables d'environnement (serveur, jamais dans le code)

| Variable | Rôle |
|---|---|
| `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD` | Serveur et identifiants de la boîte. Les trois sont obligatoires, sinon l'envoi réel est refusé (`501`). |
| `SMTP_SECURITY` | `starttls` (défaut, port 587) ou `ssl` (port 465). Pas d'option « sans TLS » ; le certificat et le nom d'hôte sont vérifiés. |
| `SMTP_PORT` | Facultatif ; déduit de `SMTP_SECURITY`. |
| `OUTREACH_SENDER_EMAIL` | **`founder@plantiers.com`** : adresse `From`/`Reply-To` de chaque message. |
| `OUTREACH_SENDER_NAME`, `_COMPANY`, `_ADDRESS` | Identité imprimée dans chaque message. L'adresse postale doit être **la vraie** (obligation d'identification de l'expéditeur). |
| `FEATURE_LIVE_SENDING` | `true` autorise l'envoi réel. |
| `OUTREACH_SANDBOX` | Actif tant qu'il n'est pas mis explicitement à `false` : seuls les destinataires de `OUTREACH_LIVE_ALLOWLIST` reçoivent quoi que ce soit. |
| `OUTREACH_LIVE_ALLOWLIST` | Adresses (`founder@plantiers.com`) ou domaines (`@plantiers.com`) autorisés pendant le sandbox. Vide = personne. |
| `SEND_KILL_SWITCH` | `true` arrête immédiatement tout envoi (se pose en redéployant). |

Le mot de passe SMTP doit être saisi dans le tableau de bord de l'hébergeur (Render : variable `sync: false`). Il n'apparaît ni dans les
journaux, ni dans une réponse d'API, ni dans la page Settings (qui n'affiche que l'hôte).

## Procédure de mise en service (dans cet ordre)

1. **Authentifier le domaine `plantiers.com`** chez votre registrar / hébergeur de messagerie : SPF, DKIM (clé fournie par votre
   messagerie), DMARC (commencer par `p=none` avec une adresse `rua=`, puis durcir). Sans cela, vos messages iront en spam. Plantiers - OutreachOS
   ne peut pas le faire à votre place : ce sont des enregistrements DNS.
2. **Identifiants SMTP** : créez un mot de passe d'application ou un compte dédié si votre messagerie l'exige (beaucoup de fournisseurs
   interdisent l'authentification SMTP avec le mot de passe principal ou la désactivent par défaut ; vérifiez chez le vôtre, ainsi que
   son quota quotidien d'envoi). Ne réutilisez pas le mot de passe de connexion.
3. **Variables** posées sur le serveur : `SMTP_*`, `OUTREACH_SENDER_*` (avec `OUTREACH_SENDER_EMAIL=founder@plantiers.com`),
   `OUTREACH_LIVE_ALLOWLIST=founder@plantiers.com`, `FEATURE_LIVE_SENDING=true`. **Laisser `OUTREACH_SANDBOX` vide (donc actif).**
   La page *Settings* doit afficher « LIVE · SANDBOX: ALLOWLISTED RECIPIENTS ONLY » et l'hôte SMTP.
4. **Test de connexion** (connecté en `owner` ou `admin`) :
   ```bash
   curl -s -X POST "$API/api/outbound/test-send" -H "Authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' -d '{"to":"founder@plantiers.com"}'
   ```
   Réponse `{"status":"sent",…}` : le serveur SMTP a **accepté** le message (ce n'est pas une preuve de remise). Ouvrez la boîte de
   réception **et le dossier spam**, puis « afficher l'original » : SPF, DKIM et DMARC doivent être `pass`. Un échec renvoie
   `{"status":"failed","error":"…"}` avec la cause (authentification, TLS, destinataire refusé…), sans le mot de passe.
5. **Limites** réglées volontairement : `PUT /api/outbound/limits` (défauts 20/jour, 100/heure, 60 s entre deux envois). Ne les relevez
   pas sans raison ; chauffez la réputation du domaine progressivement.
6. **Kill switch essayé** : posez `SEND_KILL_SWITCH=true`, redéployez, vérifiez que `test-send` répond `423`, puis retirez-le.
7. **Seulement ensuite**, et en connaissance de cause, `OUTREACH_SANDBOX=false` ouvre l'envoi à tout prospect **approuvé par un humain**
   (brouillon approuvé, prospect approuvé, non désinscrit, consentement respecté).

## Garanties techniques

- **Au plus une fois.** La ligne du message est écrite à l'état `sending` et **validée en base avant** l'appel SMTP : un plantage ou une
  coupure ne peut pas produire un second e-mail. Un message resté `sending` a une **issue inconnue** (connexion perdue pendant l'envoi) :
  vérifiez le dossier « Envoyés » de la boîte ; le système ne le renvoie jamais seul et il compte dans les limites.
- **Un échec franc** (authentification, TLS, destinataire refusé, rejet du serveur) est `failed`, ne consomme pas le quota, et le
  brouillon peut être renvoyé (nouvelle tentative).
- Un brouillon produit au plus un message `sent`, quelle que soit la clé d'idempotence.
- L'appel SMTP bloquant s'exécute dans un thread : il ne gèle pas l'API.
- Aucun test n'ouvre de connexion réseau : `smtplib` est remplacé par un enregistreur (`tests/unit/test_smtp_svc.py`,
  `tests/test_outbound_live.py`).

## Limites connues (à lire avant de compter dessus)

1. **Il faut de vrais prospects, importés par vous.** Les annuaires fictifs (`*.example`) ne sortent jamais. L'import d'une liste
   que vous avez le droit d'utiliser (origine et base légale obligatoires, `FEATURE_PROSPECT_IMPORT=true`) alimente le parcours
   « validation → brouillon → envoi ». Ne **jamais** mettre d'adresse fictive dans la liste blanche.
2. **Suivi des rebonds et des réponses : IMAP, à activer séparément.** Avec `IMAP_HOST`, `IMAP_USERNAME`, `IMAP_PASSWORD` (mêmes
   précautions que SMTP : mot de passe d'application, posé dans le tableau de bord de l'hébergeur), la boîte d'envoi est lue
   (TLS vérifié, lecture sans marquer lu, puis drapeau « lu » seulement après l'enregistrement en base) :
   - une réponse qui cite un de nos `Message-ID` passe le message à `replied` et garde un extrait de 500 caractères au plus
     (jamais le message complet, jamais le fil cité) ; les réponses automatiques (absence) sont ignorées ;
   - un « STOP » désinscrit le prospect **seulement s'il vient de l'adresse à laquelle nous avons écrit** (sinon l'événement est
     enregistré et signalé, à traiter par un humain) ;
   - un rebond **définitif** (rapport de remise `Action: failed`, `Status: 5.x.x`) passe le message à `bounced` et met l'adresse en
     liste de suppression ; un échec temporaire (4.x.x) ou un rapport illisible ne suppriment rien ;
   - un courrier qui ne se rattache à aucun de nos messages est compté « non rattaché » et ne change rien ; relire deux fois le même
     courrier n'enregistre rien deux fois.
   Déclenchement : tâche beat toutes les 5 minutes là où un worker tourne (non disponible sur le plan gratuit de Render), ou à la
   demande par le bouton « Read mailbox now » de la page *Sending* (`POST /api/outbound/sync-inbox`, rôle owner/admin).
   Sans variables IMAP, rien n'est lu : `simulate` reste réservé au dry-run, et un rebond/une réponse se traite à la main
   (`POST /api/prospects/suppressions`). Le chemin SendGrid (anciens chemins) a ses propres webhooks signés.
3. **Les anciens chemins (page Messages, lots, campagnes) n'utilisent pas SMTP.** Ils passent par SendGrid (ou mock). Sans
   `SENDGRID_FROM_EMAIL` ils restent en mock. Depuis cette tranche, chaque e-mail qu'ils envoient porte le même pied de page que
   les brouillons (identité de l'expéditeur, origine des données lue dans la source du prospect — « source non renseignée » si
   elle est vide, jamais inventée — et lien de désinscription signé) ainsi que les en-têtes `List-Unsubscribe` / one-click. Un
   destinataire sur la liste de suppression est refusé. Avec SendGrid configuré, ces chemins échouent fermé : sans identité
   `OUTREACH_SENDER_*` ou sans `lead_id` (pas de lien de désinscription possible), rien ne part. Le lien fonctionne pour tous les
   prospects, découverte ou non. WhatsApp n'est pas concerné (opt-in explicite).
4. **Base légale et registre de traitement** : à valider par un juriste (prospection B2B, droit d'opposition, information sur l'origine
   des données). Ce document n'est pas un avis juridique.
5. **Réception non vérifiée par OutreachOS** (le suivi IMAP ne lit que ce que la boîte reçoit : un message jamais rebondi n'est pas « remis ») : « sent » signifie « accepté par votre serveur SMTP », pas « arrivé en boîte ».
6. Ni cet envoi réel ni la lecture IMAP n'ont été essayés avec vos identifiants (aucun accès réseau ni secret dans l'environnement de développement) :
   la première vérification réelle est le `test-send` de l'étape 4.
