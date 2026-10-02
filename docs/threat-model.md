# Modèle de menaces (STRIDE, tranche OutreachOS)

| # | Menace | Vecteur | Parade en place | Reste à faire |
|---|---|---|---|---|
| 1 | Envoi non désiré (spam, prospect non validé) | ancien chemin d'envoi, campagne | Prospect de découverte bloqué sauf `approved` **et** `live_sending` ; refus journalisé ; le kill switch coupe aussi SendGrid et Twilio ; pause et limites appliquées à tous les chemins (point unique `send_gate`, un test statique échoue si un appel fournisseur y échappe), compteurs partagés et verrou par organisation contre les envois parallèles | — |
| 1b | Rafale d'envois (bug, boucle, compte compromis) | appels répétés (dispatch, envoi unitaire, lot, campagne) | Plafonds jour/heure et délai minimum appliqués avant l'adaptateur ; un brouillon = un seul message ; pause du compte ; `SEND_KILL_SWITCH` global (variable d'environnement, sans base) | Alerte sur les refus répétés ; plafond par utilisateur |
| 1c | Envoi réel activé par erreur | `FEATURE_LIVE_SENDING=true` | Refus 501 sans `SMTP_*` complet (échec fermé) ; **sandbox actif par défaut** : seule la liste blanche reçoit, liste vide = personne ; la check-list est dans `deployment.md` et `go-live-email.md` | Lever le sandbox reste une action humaine délibérée |
| 1d | Double envoi (plantage, coupure, rejeu) | crash entre l'envoi et l'écriture en base | Ligne `sending` validée **avant** l'appel SMTP ; issue inconnue jamais renvoyée seule ; un brouillon = au plus un message `sent` | Un message resté `sending` demande un contrôle humain du dossier « Envoyés » |
| 1e | Fuite du mot de passe SMTP | journaux, réponses d'API, page Settings, tests | Variable d'environnement seule ; exclu de `repr` ; erreurs classées et expurgées ; Settings n'affiche que l'hôte | Rotation du mot de passe si un doute existe |
| 1f | Injection d'en-têtes par un sujet | saut de ligne dans un sujet de brouillon | Retours à la ligne neutralisés dans tous les en-têtes ; corps en quoted-printable | — |
| 1g | Interception du mot de passe SMTP | serveur sans STARTTLS, certificat falsifié | TLS obligatoire, certificat et nom d'hôte vérifiés, aucun repli en clair ; le mot de passe n'est envoyé qu'après le chiffrement | — |
| 2 | Faux événements entrants (opt-out, réponses, rebonds) | webhooks publics | Signature Twilio (`X-Twilio-Signature`) et SendGrid (ECDSA) vérifiées avant toute écriture ; échec fermé en production | Fenêtre anti-rejeu sur le timestamp SendGrid |
| 3 | Fuite entre organisations | IDs devinés, listes partagées | Toutes les requêtes filtrent par `account_id` ; suppression par organisation ; test d'isolation | — |
| 4 | Forge d'un lien de désinscription | jeton falsifié | HMAC-SHA256 avec clé dérivée, comparaison à temps constant ; jeton invalide ⇒ 404 | Limitation de débit sur la route publique |
| 5 | Injection via contenu de source (HTML) | annuaire ou site hostile | Parsing en lecture seule (`html.parser`), jamais exécuté ni rendu ; contenu stocké en JSON/texte, jamais interprété | Échapper à l'affichage dans l'UI ; borner la taille des champs et des pages (aujourd'hui seulement bornée par les fixtures) |
| 6 | SSRF / scraping abusif | source réseau | Aucune source ni fetcher réseau implémenté ; source inconnue ⇒ 400 | À la création d'un fetcher : liste d'hôtes autorisés, refus des IP privées, `robots.txt`, délai, timeouts |
| 7 | Contournement de la revue humaine | appel direct à l'API | Décisions réservées à `owner`/`admin` ; chaque décision auditée avec l'acteur | Double validation optionnelle |
| 8 | Perte de preuves | rollback sur erreur HTTP | Refus d'envoi validés avant le 403 | Étendre à toute écriture d'audit suivie d'une exception |
| 9 | Données personnelles résiduelles après effacement | copies dans sources/brouillons | Effacement ciblé sur toutes les copies connues + suspension ; test | Purge programmée, sauvegardes **[à valider]** |
| 10 | Secrets exposés | logs, tests, dépôt | Aucune clé dans le code ; tests à valeurs aléatoires ; GitGuardian en CI ; webhooks refusés sans secret en production | Rotation documentée |
| 11 | Dépendances | supply chain | Aucune dépendance ajoutée par cette tranche ; script tiers et suivi de session retirés de `index.html` | Audit du `requirements.txt` (~170 paquets, beaucoup probablement inutiles) |
| 12 | Déni de service par import massif | `discovery/run` | Source locale bornée ; réservé aux décideurs | Quotas par organisation (voir `cost-control.md`) |

Hors périmètre actuel : attaques sur Celery/Redis, durcissement des en-têtes de l'API, chiffrement au repos (délégué à l'hébergeur).
