# Sources de découverte

Page **Sources** (`/app/sources`) et API `POST /api/sources/discover` : une seule interface pour découvrir des entreprises à partir de
données ouvertes ou officielles. Rien n'est envoyé depuis cette page : les résultats retenus entrent dans la **file de revue**
(prospects « à valider »), avec leur source, leur licence et l'enregistrement brut d'origine.

## Fournisseurs

| Nom | Type | Couverture | Clé | Coût | Limite fournisseur |
|---|---|---|---|---|---|
| `world_fixture` | local (aucun réseau) | démo fictive : ~20 pays, tous continents, 7 verticales, domaines `.example` | non | 0 | aucune |
| `openstreetmap` | réseau (`FEATURE_EXTERNAL_SOURCES`) | monde entier, ce que les contributeurs ont publié (téléphone, e-mail, site) | non | 0 | serveurs Overpass publics : usage léger, cache 10 min |
| `registry_fr` | réseau (`FEATURE_EXTERNAL_SOURCES`) | entreprises françaises actives (SIREN, siège, activité NAF) — **ni e-mail, ni téléphone, ni site** | non | 0 | 7 requêtes/s par IP |

Verticales : `restaurants, bakeries, beauty, hotels, shops, crafts, offices` (le registre couvre `restaurants, bakeries, beauty, hotels,
offices` via les codes NAF). L'import CSV/JSON garde sa page dédiée (`/app/prospects/import`).

## Appels

```bash
# Démo, sans clé ni réseau
curl -s -X POST "$API/api/sources/discover" -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"provider":"world_fixture","vertical":"restaurants","limit":25,"country":"JP"}'

# OpenStreetMap autour de Lyon (3 km), pays obligatoire pour les sources réseau
curl -s -X POST "$API/api/sources/discover" -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"provider":"openstreetmap","vertical":"bakeries","lat":45.764,"lon":4.8357,"radius_m":3000,"country":"FR","limit":50}'

curl -s "$API/api/sources/runs/$RUN_ID?offset=25&limit=25" -H "Authorization: Bearer $TOKEN"          # pagination
curl -s -X POST "$API/api/sources/runs/$RUN_ID/add" -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"external_ids":["node/123"],"attestation":true}'                                                  # → file de revue
```

Réponse de `discover` : `run_id`, `total`, `duplicates_merged`, `truncated`, `license_note` et, pour chaque lieu, ses champs publiés,
sa source (`source_url`) et ses **signaux** (`detected | not_detected | unknown`, avec la preuve). Les signaux qui demandent de
charger le site restent `unknown` à ce stade : « inconnu » n'est jamais un verdict.

## Garde-fous

- **Limites de débit** (429 + `Retry-After`, refus journalisé) : 30 requêtes/minute par adresse IP, 20/minute par utilisateur
  (il n'existe pas de clé d'API par client : l'utilisateur authentifié en tient lieu), et par organisation et fournisseur
  (`RateLimit` de l'adaptateur : 60/min démo, 6/min OSM, 10/min registre). En mémoire, par processus : elles se remettent à zéro au
  redémarrage. Derrière Render, définir `FORWARDED_ALLOW_IPS=*` pour que l'IP du client (et non celle du proxy) serve de clé.
- **Validation stricte** : fournisseur et verticale connus, `limit` 1–100, `lat/lon` ensemble et dans leurs bornes, rayon borné par
  fournisseur (OSM 10 km, registre 50 km), pays ISO sur 2 lettres. Les sources réseau exigent une position **et** un pays.
- **Audit** : chaque découverte (`sources.discover`), refus (`sources.refused`) et ajout (`sources.added`) est journalisé avec les
  paramètres, les comptes et l'empreinte SHA-256 des données brutes (jamais les lieux eux-mêmes).
- **Provenance et données brutes** : chaque lieu ajouté garde sa source, son URL, la licence et son enregistrement brut d'origine
  (plafonné à 4 Ko) dans `prospect_sources`. Les résultats d'une découverte restent 30 minutes en mémoire (410 ensuite : relancer).
- **Doublons** : un seul résultat par établissement (même domaine propre, même téléphone ou même nom + ville).
- **Feature flags** : sources réseau = `FEATURE_EXTERNAL_SOURCES`; ajout de données réelles = `FEATURE_PROSPECT_IMPORT` (la démo
  s'ajoute sans). Attestation obligatoire. Rien n'est envoyé : l'envoi garde ses propres verrous (dry-run, sandbox, kill switch).

## Sources volontairement absentes

- **Google Places / SerpAPI** : payant, et les conditions de Google interdisent de conserver ses données (hors identifiant de lieu) ;
  SerpAPI extrait des pages Google. **Bing Maps** : conditions comparables. Aucun des trois ne peut alimenter une base de prospects.
- **LinkedIn, réseaux sociaux** : jamais (interdit par le projet et par leurs conditions).
- **Apollo, Clearbit, Crunchbase** : clés payantes. L'interface `DiscoveryAdapter` permet de les brancher plus tard (une classe, un
  enregistrement dans `routes/sources.py::adapters`), désactivés tant qu'aucune clé n'est configurée. Non implémentés ici.

## Ajouter une source

1. Écrire un adaptateur dans `services/outreach_os/` qui implémente `DiscoveryAdapter` (`name`, `label`, `license_note`, `kind`,
   `trust_absence`, `rate_limit`, `verticals`, `max_radius_m`, `fetch(params) -> FetchResult`), client HTTP **injecté**.
2. Le déclarer dans `routes/sources.py::adapters()`.
3. Tests sur fixtures (aucun appel réseau réel) : voir `backend/tests/unit/test_discovery_sources.py`.
4. Vérifier ses CGU et son `robots.txt` avant de l'activer.

## Limites connues

- `registry_fr` n'a pas été essayé contre le service réel (aucun accès sortant depuis le développement) : le format des champs vient de
  la documentation publique et est lu défensivement ; premier essai réel à faire après déploiement.
- Les résultats d'une découverte vivent en mémoire d'un seul processus (instance unique sur Render gratuit).
