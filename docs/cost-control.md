# Contrôle des coûts

## Coût d'exécution

La tranche actuelle n'engage **aucun coût externe** : sources et sites viennent de fixtures locales, aucun appel réseau,
aucun fournisseur d'e-mail, aucun appel à un LLM (les brouillons sont rendus par un gabarit déterministe).
`usage_records` mesure néanmoins ce qui serait facturable plus tard :

| `kind` | Quantité | Écrit par |
|---|---|---|
| `discovery_run` | 1 par exécution | `POST /prospects/discovery/run` |
| `signals_analyzed` | entités analysées | idem |
| `drafts_generated` | 1 par brouillon créé | `POST /prospects/{id}/drafts` |
| `messages_dispatched` | 1 par message passé par l'adaptateur (`meta.dry_run`) | `POST /outbound/dispatch` |

Lecture : `GET /api/prospects/settings` → `usage`. Les rejeux idempotents (même clé d'idempotence, mêmes données) n'ajoutent ni
source, ni signal, ni score, ni brouillon : relancer un run est quasi gratuit.

## Crédits et modèles d'outreach (en place)

Le travail d'IA est plafonné par des **crédits** (`services/outreach_os/credits.py`, pur ; `services/credit_gate.py` ; `GET /api/usage/credits`,
`PUT /api/usage/model`). Deux fenêtres : la **session** de 5 h, qui commence à la première dépense, et le **jour** (heure de Paris).
Une dépense qui dépasserait l'une des deux est refusée **avant** tout appel au fournisseur (`402 credits_exhausted`, avec la fenêtre et
l'heure de réinitialisation) ; un appel qui échoue ne coûte rien (la dépense est écrite après la réponse, `usage_records.kind = 'credits'`).

| Modèle | Crédits par message | IA |
|---|---|---|
| Plantiers Gabarit | 0 | non : le modèle approuvé de la campagne, rendu avec les faits détectés |
| Plantiers Rapide | 1 | oui, 90 mots au plus |
| Plantiers Équilibre (défaut) | 2 | oui, 140 mots au plus |
| Plantiers Précision | 4 | oui, 180 mots au plus |

Limites : `CREDITS_PER_DAY` (100) et `CREDITS_PER_SESSION` (30). Le modèle choisi s'applique au composeur IA et aux brouillons
automatiques ; un lot de brouillons s'arrête dès que les crédits sont épuisés et reprend au tour suivant. Le compte de la fenêtre est fait
sous un verrou de la ligne du compte ; des brouillons préparés en parallèle peuvent la dépasser d'au plus quelques crédits.

## Leviers de maîtrise prévus (non implémentés)

- ~~Quota quotidien et délai minimal~~ : **en place** pour le dispatch (`/api/outbound/limits`, défauts 20/jour, 100/heure,
  60 s), **et** pour les anciens chemins (envoi unitaire, lot, campagnes, Celery) via `services/send_gate.py`, avec des
  compteurs partagés.
- Plafond d'enregistrements d'usage par jour et par organisation pour limiter les imports.
- Si un fetcher réseau est ajouté : délai entre requêtes, timeouts, taille maximale de page, cache par `content_hash`.
- Si un LLM est ajouté pour la rédaction : budget mensuel en `usage_records`, modèle le plus petit suffisant, mise en cache.

## Budget de développement (session cloud limitée)

Une fonctionnalité = une branche = une PR, avec ses tests ; lancer d'abord les tests ciblés, puis la suite complète une seule
fois avant de pousser ; ne pas relancer des boucles de correction sans lire l'erreur.
