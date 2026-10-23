# Intégrations : ce que Settings affiche, et comment chaque service s'active

La page **Settings → Integrations** liste **chaque** intégration du serveur, avec un statut **calculé côté serveur** à partir de sa vraie
configuration (`GET /api/settings/integrations`, `services/integrations_status.py`, pur et testé). Rien n'est codé en dur dans l'interface :
une clé absente, un paquet manquant ou un drapeau coupé s'affichent comme tels, avec la raison et le **nom exact des variables** à poser.
La page se relit seule toutes les 30 s (onglet visible) : après un redéploiement, les statuts se mettent à jour sans recharger.

## Statuts
| Statut | Sens |
|---|---|
| `ready` | fonctionne tel que configuré (ou : le test a réussi, affiché `VERIFIED · n ms`) |
| `unchecked` | rien ne manque, mais seul un test réel peut le prouver : bouton **TEST NOW** |
| `partial` | fonctionne avec une limite, ou posé mais inutilisable tel quel (ex. `TWILIO_ACCOUNT_SID` qui ne commence pas par `AC`) |
| `missing` | non configuré : le produit refuse d'agir et dit quoi configurer (aucun envoi simulé, aucun texte tout fait) |
| `blocked` | arrêt de sécurité ou configuration qui fait échouer envois ou liens (kill switch, live sans SMTP, URL publique locale en production) |
| `off` | désactivé volontairement (drapeau, dry-run) ou pas encore utile (signature d'un webhook dont le fournisseur n'est pas configuré) |

## Les clés ne se saisissent jamais dans l'application
Aucun champ de la page ne reçoit un secret, et l'API ne renvoie que des **noms** de variables, jamais une valeur. Pour activer un service :
1. hébergeur (Render → votre service API → *Environment*) : ajoutez les variables indiquées dans l'encadré jaune de la carte (bouton « copy the names ») ;
2. redéployez ; 3. revenez sur Settings : le statut a changé, lancez **TEST NOW**.

## Tests réels (`POST /api/settings/integrations/{id}/test`, propriétaire/admin, 10 par minute et par organisation)
Tous en lecture seule : **aucun message n'est envoyé à une personne**. Un test sur un service non configuré répond `skipped` (jamais un faux succès).
| Id | Ce que fait le test |
|---|---|
| `database` | un aller-retour `SELECT 1`, latence mesurée |
| `osm` | une requête d'état par serveur Overpass, l'un après l'autre (jamais en rafale) |
| `registry` | une requête d'exemple au registre des entreprises ; ignoré si `FEATURE_EXTERNAL_SOURCES` est coupé |
| `smtp` | connexion TLS + authentification, **sans envoi** (pas de `MAIL FROM`) |
| `imap` | connexion TLS + ouverture du dossier **en lecture seule** ; aucun message lu, marqué ou modifié |
| `sendgrid` | lecture des permissions de la clé |
| `twilio` | lecture de la fiche du compte (SID + jeton) |
| `geocoder` | exécuté **dans votre navigateur** (c'est lui qui appelle ce service), un seul appel |

L'IA n'a pas de test : appeler un modèle est facturé par son fournisseur, rien n'en appelle tant qu'aucune clé n'est posée.
Les erreurs renvoyées ne contiennent ni identifiant ni mot de passe : seulement l'étape atteinte et la classe d'erreur.

## Fiches

<a id="database"></a>
### Base de données
`DATABASE_URL`. Affiche le type d'hôte (Supabase session pooler, direct, Render…), le port et la latence mesurée. L'hôte direct Supabase est
IPv6 seulement : un hébergeur sans IPv6 (Render) ne l'atteint pas, utilisez le **Session pooler** (port 5432), voir `docs/supabase.md`.

<a id="public_url"></a>
### URL publique
`PUBLIC_BASE_URL`, `APP_ENV`. Base du lien de désinscription de chaque e-mail : en production, une adresse locale ou absente rend ce lien
inutilisable (statut `blocked`) ; `http://` non chiffré = `partial`.

<a id="osm"></a>
### OpenStreetMap (Overpass)
Sans clé. `OVERPASS_ENDPOINTS` (facultatif) remplace les serveurs publics par une instance à vous. Les serveurs en pause (après des échecs) sont listés.
Si aucun serveur ne répond depuis l'hébergeur, la recherche sur carte bascule explicitement sur le navigateur (`docs/map-search.md`).

<a id="geocoder"></a>
### Recherche de villes (api-adresse.data.gouv.fr)
Sans clé, appelée depuis le navigateur.

<a id="registry"></a>
### Registre des entreprises (France)
Sans clé. Source réseau : demande `FEATURE_EXTERNAL_SOURCES=true` (voir `docs/sources.md`).

<a id="sender"></a>
### Identité d'expéditeur
`OUTREACH_SENDER_NAME`, `OUTREACH_SENDER_COMPANY`, `OUTREACH_SENDER_ADDRESS`, `OUTREACH_SENDER_EMAIL` : requis dans chaque e-mail (conformité).

<a id="sending_mode"></a>
### Mode d'envoi
`FEATURE_LIVE_SENDING`, `SEND_KILL_SWITCH`, `OUTREACH_SANDBOX`, `OUTREACH_LIVE_ALLOWLIST`, `OUTREACH_LIVE_PHONES`. Dry-run par défaut ; `LIVE · SANDBOX` n'atteint que la liste
autorisée ; le kill switch arrête tout. Procédure : `docs/go-live-email.md`.

<a id="smtp"></a>
### SMTP
`SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD` (+ `SMTP_SECURITY`, `SMTP_PORT`). Le canal réel pour les prospects. Posé mais invalide
(sécurité inconnue, port hors plage) : `partial`.

<a id="imap"></a>
### IMAP
`IMAP_HOST`, `IMAP_USERNAME`, `IMAP_PASSWORD` (+ `IMAP_PORT`, `IMAP_FOLDER`). Lit réponses, rebonds et STOP dans la boîte d'envoi ; sans lui, tout se traite à la main.

<a id="sendgrid"></a>
### SendGrid (facultatif)
`SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`. Alternative à SMTP pour les messages CRM et les campagnes (SMTP passe en premier quand il est complet). Sans clé : refus explicite, rien n'est envoyé ni enregistré comme envoyé.

<a id="twilio"></a>
### Twilio WhatsApp (facultatif)
`TWILIO_ACCOUNT_SID` (commence par `AC`), `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`. Opt-in explicite requis pour chaque contact ; pendant le sandbox, seuls les numéros de `OUTREACH_LIVE_PHONES` reçoivent un message. Test : page *Sending* → « Send test WhatsApp ».

<a id="twilio_webhook"></a>
### Signature des webhooks Twilio
`TWILIO_AUTH_TOKEN` + `TWILIO_WEBHOOK_URL` (l'URL publique exacte configurée dans la console Twilio, requise derrière un proxy). En production, un appel non signé est refusé.

<a id="sendgrid_webhook"></a>
### Signature des webhooks SendGrid
`SENDGRID_WEBHOOK_PUBLIC_KEY`. Même règle : échec fermé en production.
Les deux signatures sont `off` (« NOT NEEDED YET ») tant que leur fournisseur n'est pas configuré, puis `partial` s'il manque la clé ou l'URL.

<a id="ai"></a>
### Compositeur IA
`EMERGENT_LLM_KEY` et le paquet optionnel `emergentintegrations` (index privé, hors `requirements.txt`). Tant que les deux ne sont pas là, le
compositeur **refuse** (HTTP 503, aucun texte tout fait qui ferait semblant d'être un message) et la page affiche `OFF · NOTHING IS GENERATED` avec la raison ; il n'affiche `LIVE · MODEL CALLED` que si le modèle est réellement appelable.
