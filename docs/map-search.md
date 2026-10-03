# Recherche sur carte (OpenStreetMap)

Page **Map search** (`/app/map`) : on déplace une carte interactive (Leaflet, tuiles OpenStreetMap) sur une ville, on choisit une
catégorie, « Search this area » interroge l'API Overpass (données OpenStreetMap) **en direct** et affiche les établissements
réels de la zone avec ce que leurs contributeurs ont publié : adresse, téléphone, e-mail, site web. Gratuit, sans clé, sans compte.

## Mes prospects sur la carte
Les prospects déjà importés qui ont une position (importés depuis la carte, ou depuis un fichier avec colonnes `lat`/`lon`) sont
dessinés en **carrés** (bleu : à valider, vert : approuvé, rouge : refusé), cliquables vers leur fiche. Un lieu déjà importé n'est
plus proposé comme résultat de recherche (reconnu par son identifiant OpenStreetMap). Endpoint : `GET /api/map/prospects`.

## D'où part la requête Overpass
Les serveurs Overpass publics répondent mal à l'adresse partagée de l'hébergeur de l'API (délais, « network unreachable »). La recherche
passe donc **par le navigateur** : `POST /api/map/query` (le serveur construit et valide la requête, limite 6/min/organisation), le
navigateur interroge lui-même un serveur Overpass public (CORS ouvert, 15 s par serveur), puis `POST /api/map/parse` (12/min) renvoie
la réponse au **même analyseur** que la recherche côté serveur : seuls les champs publiés sont gardés, rien n'est complété. Si le
navigateur n'atteint aucun serveur, la recherche côté serveur (`POST /api/map/search`) sert de repli et le message d'erreur nomme
les deux causes. La réponse transmise à `/map/parse` n'est conservée nulle part ; l'import reste attesté et audité.

## Ce qui est affiché, et ce qui ne l'est pas
- Uniquement les champs publiés dans OpenStreetMap (`phone`, `email`/`contact:email`, `website`, `addr:*`). Un champ absent s'affiche
  « not published » : rien n'est deviné ni complété. Beaucoup d'établissements n'ont pas d'e-mail dans OSM.
- Licence ODbL 1.0 : la mention « © OpenStreetMap contributors » est affichée sur la carte et enregistrée dans la source de chaque
  prospect (page OpenStreetMap de l'élément, en provenance).
- Zone limitée à ~22 × 33 km, 300 résultats au plus, 6 recherches par minute et par organisation, cache de 10 minutes.

## Trouver l'e-mail quand OSM n'en a pas
À l'import de la sélection, l'option « look for a public contact e-mail » lit la page d'accueil **du site propre** de chaque
établissement (`robots.txt` respecté, 25 sites au plus) et ne retient qu'un lien `mailto:` du **même domaine** que le site. Rien n'est
déduit d'un nom, rien n'est lu dans le texte ou les scripts, adresses techniques (`noreply@`…) refusées. L'origine est dans
l'historique d'audit (`prospect.email_found`). Les réseaux sociaux, Google, LinkedIn, annuaires d'avis ne sont jamais consultés.

## Activer
Variables du serveur : `FEATURE_EXTERNAL_SOURCES=true` (carte + lecture des sites) et `FEATURE_PROSPECT_IMPORT=true` (import de la sélection).
Redéployer. Rien n'est envoyé : les lieux importés deviennent des prospects **à valider** (file de revue), puis brouillon, puis envoi
selon les garde-fous habituels (liste blanche, désinscription, limites).

## Limites connues
- Les données OSM sont celles de la communauté : parfois anciennes ou incomplètes. Vérifier avant d'écrire.
- Les serveurs Overpass publics peuvent être lents ou occupés (erreur 502 explicite, réessayer).
- Pas de collecte depuis Google Maps, Pages Jaunes, LinkedIn ou réseaux sociaux : leurs conditions l'interdisent.
- Un e-mail nominatif (personne physique) trouvé sur un site reste une donnée personnelle : base légale, information et
  désinscription s'appliquent, voir `docs/compliance.md`.
