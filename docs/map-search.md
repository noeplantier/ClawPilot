# Recherche sur carte (OpenStreetMap)

Page **Map search** (`/app/map`) : on déplace une carte interactive (Leaflet, tuiles OpenStreetMap) sur une ville, on choisit une
catégorie, « Search this area » interroge l'API Overpass (données OpenStreetMap) **en direct** et affiche les établissements
réels de la zone avec ce que leurs contributeurs ont publié : adresse, téléphone, e-mail, site web. Gratuit, sans clé, sans compte.

## Mes prospects sur la carte
Les prospects déjà importés qui ont une position (importés depuis la carte, ou depuis un fichier avec colonnes `lat`/`lon`) sont
dessinés en **carrés** (bleu : à valider, vert : approuvé, rouge : refusé), cliquables vers leur fiche. Un lieu déjà importé n'est
plus proposé comme résultat de recherche (reconnu par son identifiant OpenStreetMap). Endpoint : `GET /api/map/prospects`.

## Une recherche = un job enregistré
`POST /api/map/search` crée un job (`map_search_jobs` : zone, catégorie, statut, source, nombre de résultats, erreur, durée,
auteur, organisation) et répond tout de suite (`202`). Un exécutant en arrière-plan du processus de l'API :
1. lit le **cache** (`source_cache`, clé = version de la requête + zone arrondie à 0,005° + catégorie, TTL 6 h) ;
2. sinon envoie **une** requête Overpass (une à la fois dans tout le processus, serveurs essayés à tour de rôle, 15 s chacun, IPv4,
   User-Agent identifié ; un serveur qui vient d'échouer est essayé en dernier pendant 5 minutes, jamais écarté) ;
3. normalise, **dédoublonne** (même identifiant OSM, ou même nom au même endroit : on garde l'entrée la plus complète) et enregistre
   les lieux dans `map_search_results` ;
4. passe le job à `succeeded` ou `failed` avec un code (`overpass_timeout`, `overpass_busy`, `overpass_unreachable`,
   `overpass_bad_answer`, `overpass_too_large`, `job_lost`, `internal_error`) et un message qui nomme chaque serveur.

La page interroge `GET /api/map/search/{id}` toutes les 1,5 s puis lit `GET /api/map/search/{id}/places`. Au rechargement (ou depuis un
autre appareil) la dernière recherche réussie de l'organisation revient depuis la base (`GET /api/map/search`). Un job resté
`queued/running` plus de 3 minutes (redémarrage de l'instance) est déclaré `job_lost`. Les jobs de plus de 30 jours et leurs lieux
sont supprimés à la création d'une nouvelle recherche.

**Les lieux enregistrés ne sont pas des prospects** : c'est une zone de travail. Un lieu ne devient prospect que par l'import attesté
(origine, base légale, liste de suppression, audit), conformément à la conformité du projet.

**Repli navigateur, explicite** : quand l'échec vient des serveurs publics, la réponse du job contient `fallback` (la requête et les
serveurs) et la page propose « Retry from my browser » : le navigateur interroge lui-même un serveur Overpass, puis
`POST /api/map/search/{id}/ingest` envoie la réponse au **même analyseur** ; seul un job `failed` peut être complété ainsi
(12/min/organisation, 1000 éléments au plus). Ce n'est jamais automatique.

**Diagnostic** : la page *System health* (`/app/system`, `GET /api/system/health`) montre la base, les migrations, le cache et les
recherches des dernières 24 h ; le bouton « Check from the server » (`POST /api/system/health/overpass`, 3/min) interroge la page de
statut de chaque serveur Overpass depuis l'API elle-même.

## Ce qui est affiché, et ce qui ne l'est pas
- Uniquement les champs publiés dans OpenStreetMap (`phone`, `email`/`contact:email`, `website`, `addr:*`). Un champ absent s'affiche
  « not published » : rien n'est deviné ni complété. Beaucoup d'établissements n'ont pas d'e-mail dans OSM.
- Licence ODbL 1.0 : la mention « © OpenStreetMap contributors » est affichée sur la carte et enregistrée dans la source de chaque
  prospect (page OpenStreetMap de l'élément, en provenance).
- Zone limitée à ~22 × 33 km, 300 résultats au plus, 6 recherches par minute et par organisation, cache de 10 minutes.

## Un clic sur un point : l'établissement entre dans le CRM
Cliquer un point ouvre sa fiche (ce que la carte publie, « not published » pour le reste). Après avoir coché une fois l'attestation
(mémorisée dans ce navigateur : « j'ai le droit d'utiliser ces coordonnées professionnelles pour de la prospection B2B, intérêt légitime,
et je respecterai les oppositions »), **ADD TO CRM** fait en une action ce que faisait le formulaire d'import pour un seul lieu :
import attesté (origine = page OpenStreetMap du lieu, base légale, liste de suppression, audit), lecture facultative du site propre pour un
e-mail public, puis **votre décision d'approuver** ce prospect (tracée dans l'audit : `prospect.approved`, `via: map_quick_add`).
**FOR REVIEW** laisse la décision à la file de revue. Le résultat reste affiché (e-mail trouvé sur le site ou publié sur la carte,
téléphone, site lu ou non) avec les liens vers le CRM et la fiche. Un lieu déjà ajouté est complété, jamais dupliqué ; un contact sur la
liste de suppression est refusé (`409 suppressed`). **Rien n'est envoyé** : contacter exige toujours un brouillon approuvé et les règles
d'envoi. API : `POST /api/map/places/add` (owner/admin, `FEATURE_PROSPECT_IMPORT`, 60 par minute et par organisation).
Les prospects ajoutés apparaissent dans **Leads** (avec leur statut de revue), la file de revue, les suggestions de campagne et la carte.

## Trouver l'e-mail quand OSM n'en a pas
Avec l'option « look for a public contact e-mail » (import de la sélection, ou ajout d'un point), le serveur lit la page d'accueil **du
site propre** de chaque établissement (`robots.txt` respecté, 25 sites au plus) ; si elle ne publie pas d'adresse, il lit **une seule page
de plus : la page contact que l'accueil lui-même désigne** (même site, adresse de type `/contact`, `/nous-contacter`, `/contact-us`…).
Il ne retient qu'un lien `mailto:` du **même domaine** que le site. Rien n'est déduit d'un nom, rien n'est lu dans le texte ou les
scripts, aucune autre page n'est parcourue, adresses techniques (`noreply@`…) refusées. L'origine (accueil ou page contact) est dans
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

## Mesure faite depuis l'hébergeur de l'API (23 octobre 2026)
Page *System health* → « Check from the server », depuis Render (Francfort, offre gratuite) : `overpass-api.de` **connexion refusée**,
`overpass.private.coffee` et `overpass.kumi.systems` **délai de lecture dépassé (6 s)**, `maps.mail.ru` **HTTP 504**. Les serveurs publics
refusent ou ralentissent cette adresse partagée : ce n'est pas un défaut de la requête. Le repli navigateur fonctionne indépendamment
(l'adresse du visiteur n'est pas celle de l'hébergeur). Solutions durables : un autre serveur public qui répond (`overpass.openstreetmap.fr`
est ajouté, à vérifier avec la même mesure), un Overpass auto-hébergé (`OVERPASS_ENDPOINTS`), ou une API hébergée ailleurs.
