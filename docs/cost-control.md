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

## Leviers de maîtrise prévus (non implémentés)

- ~~Quota quotidien et délai minimal~~ : **en place** pour le dispatch (`/api/outbound/limits`, défauts 20/jour, 100/heure,
  60 s). Les anciens chemins d'envoi (campagnes) ne les appliquent pas encore.
- Plafond d'enregistrements d'usage par jour et par organisation pour limiter les imports.
- Si un fetcher réseau est ajouté : délai entre requêtes, timeouts, taille maximale de page, cache par `content_hash`.
- Si un LLM est ajouté pour la rédaction : budget mensuel en `usage_records`, modèle le plus petit suffisant, mise en cache.

## Budget de développement (session cloud limitée)

Une fonctionnalité = une branche = une PR, avec ses tests ; lancer d'abord les tests ciblés, puis la suite complète une seule
fois avant de pousser ; ne pas relancer des boucles de correction sans lire l'erreur.
