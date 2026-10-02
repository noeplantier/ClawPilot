# Modèle de menaces (STRIDE, tranche OutreachOS)

| # | Menace | Vecteur | Parade en place | Reste à faire |
|---|---|---|---|---|
| 1 | Envoi non désiré (spam, prospect non validé) | ancien chemin d'envoi, campagne | Prospect de découverte bloqué sauf `approved` **et** `live_sending` ; refus journalisé ; le kill switch coupe aussi SendGrid et Twilio | Appliquer pause et limites aux anciens chemins d'envoi (campagnes) |
| 1b | Rafale d'envois (bug, boucle, compte compromis) | appels répétés à `dispatch` | Plafonds jour/heure et délai minimum appliqués avant l'adaptateur ; un brouillon = un seul message ; pause du compte ; `SEND_KILL_SWITCH` global (variable d'environnement, sans base) | Alerte sur les refus répétés ; plafond par utilisateur |
| 1c | Envoi réel activé par erreur | `FEATURE_LIVE_SENDING=true` | Aucun adaptateur réel : refus 501 (échec fermé) ; la check-list de mise en production est dans `deployment.md` | — |
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
