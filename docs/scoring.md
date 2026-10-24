# Signaux et score

Chaque signal est une observation **à trois états** avec sa preuve : `detected` (observé, et cela dit ce que décrit le signal),
`not_detected` (observé, et cela dit le contraire), `unknown` (non observable : rien n'a été chargé, pas de date, non applicable).
**`unknown` ne compte ni pour ni contre un prospect** ; on ne conclut jamais « mauvais prospect » d'une absence.

## Signaux implémentés (9)

| Clé | Ce qu'il observe | Poids par défaut |
|---|---|---|
| `no_website` | pas de site propre dans la source (un profil Facebook/Google ne compte pas) | 30 |
| `website_unreachable` | la page d'accueil répond en erreur (404/410/5xx hors refus anti-robot) ou le nom d'hôte n'existe pas | 25 |
| `booking_page_missing` | aucun lien ni mot de réservation sur la page d'accueil | 20 |
| `not_mobile_friendly` | pas de `<meta viewport width=device-width>` (heuristique, page non rendue) | 15 |
| `public_contact_present` | téléphone ou e-mail publié dans la source | 10 |
| `stale_listing` | fiche non mise à jour depuis plus de `stale_days` (365 par défaut) | 10 |
| `incomplete_listing` | au moins 2 champs clés manquants **dans cette source** | 10 |
| `outdated_technology` | marqueurs sur la page d'accueil : jQuery < 3, WordPress < 5, Joomla < 3, Drupal < 8, balises obsolètes (`font`, `center`, `marquee`, `blink`, `frameset`), Flash | 10 |
| `no_social_presence` | aucun lien vers un réseau social (Facebook, Instagram, LinkedIn, TikTok, X, YouTube, Pinterest) **sur la page d'accueil du site propre** | 5 |

Les deux derniers lisent uniquement le HTML d'accueil récupéré avec l'option « vérifier les sites » (`robots.txt` respecté,
`FEATURE_EXTERNAL_SOURCES`) ; sans HTML ils restent `unknown`. Ils ne consultent **jamais** un réseau social : on cherche seulement un
lien dans la page de l'entreprise. Leur preuve rappelle leurs limites (« autres pages non vérifiées »).
Signaux non réalisés : « avis récents sans réponse » et « fiche Google obsolète » exigent l'API Google Places, payante et dont les
conditions interdisent de conserver les données.

## Score

`score = somme des poids des signaux detected`, plafonné à 100, avec la **couverture** (part des signaux pondérés observables). Les
pondérations et `stale_days` sont une configuration versionnée et immuable : `PUT /api/prospects/score-config` ajoute une
version ; chaque score garde sa version et son empreinte, et sa ventilation ligne par ligne (signal, état, poids, points, preuve).
Une ancienne version sans les nouvelles clés les compte à poids 0.

Recalcul : `POST /api/prospects/{id}/rescore` (depuis les signaux déjà observés, rien n'est relu) et
`POST /api/campaigns/{id}/rescore` (tous les leads de la campagne : prospects de découverte et leads CRM ; 3 lots/minute et 500
leads au plus par organisation ; journalisé `campaign.rescored`). Un prospect de découverte n'entre dans une campagne que s'il est
approuvé **et** que l'envoi réel est activé.

## Rejeter un signal faux

Dans la fiche prospect, « This is wrong » (owner/admin) sur un signal `detected` ou `not_detected`, avec une raison (≥ 5 caractères) :
`POST /api/prospects/{id}/signals/{clé}/dismiss`, puis `…/restore` pour annuler.

- C'est une décision **en ajout seul** (`signal_dismissals`) : l'observation reste telle qu'elle a été faite et reste affichée.
- Tant qu'elle est en vigueur, le signal est lu comme **`unknown`** (jamais « not_detected ») : il ne rapporte plus de points, le
  score est recalculé (nouvelle ligne de score, même version de configuration), et **aucun brouillon ne peut l'énoncer**.
- Une nouvelle découverte ou une relecture du site ne l'écrase pas : la décision humaine reste en vigueur jusqu'à `restore`.
- Audit : `signal.dismissed` / `signal.restored` avec la clé, le score obtenu et la longueur de la raison (jamais son texte).
  La raison est effacée par la suppression d'un prospect (`/erase`).

## Ajouter un signal

1. Dans `services/outreach_os/signals.py` : une constante, une entrée dans `SIGNAL_LABELS`, une fonction `_mon_signal(listing,
   snapshot)` qui renvoie un `SignalResult` à trois états **avec la preuve et ses limites**, et son ajout dans `analyze` (même ordre
   que `ALL_SIGNALS`).
2. Un poids par défaut dans `services/outreach_os/scoring.py::DEFAULT_WEIGHTS` (le validateur refuse une clé inconnue).
3. Tests unitaires sur fixtures HTML/JSON (`backend/tests/fixtures/`), y compris le cas « non observable → `unknown` ».
4. Aucune migration : les signaux sont des lignes de `prospect_signals` identifiées par leur clé.

## Chaleur d'un lead (heat) : le classement « chaud d'abord »
Un lead est d'autant plus **chaud** qu'il porte d'informations **réelles** et qu'il a un bon score. Rien n'est inventé :
- `information` = part des 8 champs suivis réellement connus (e-mail, téléphone, site, ville, société, catégorie, pays, poste). Un champ vide,
  « unknown » ou la valeur par défaut d'un import (« unspecified ») est **inconnu**, jamais compté ni rempli.
- `heat = (score + information + 1) / 2` (entiers, arrondi vers le haut à .5). Un lead **jamais scoré** est classé sur l'information seule et
  l'affiche (`scored: false`) : « non scoré » n'est pas 0. Pour un lead du CRM, un score de 0 veut dire « pas encore scoré ».
- Paliers : **hot ≥ 65**, **warm ≥ 40**, **cold** en dessous. Un lead à **80 ou plus** est **TOP** (`heat.top`) : c'est lui qu'on traite en premier. Il a
  sa pastille « TOP » et sa voie dédiée dans Leads et Review queue (les voies se recouvrent : un TOP est aussi hot).
- **Lead vide** : ni e-mail, ni téléphone, ni site (`heat.has_contact = false`) : rien pour le joindre. Un bon score ne le rend pas joignable. Les listes
  le **masquent par défaut** (Leads, Review queue, Prospects, sélecteur de campagne) et disent combien ils sont (« 3 empty leads hidden »), avec un bouton
  pour les afficher ; le choix est gardé dans le navigateur. Côté API : `GET /api/prospects?hide_empty=true` et `GET /api/prospects/queues?hide_empty=true`
  (les totaux suivent le filtre ; `empty` est toujours renvoyé, `top` aussi). La page Leads reçoit tous les leads et applique `heat.has_contact`.
- Un prospect de découverte est classé sur son **dernier score de prospect** (`prospect_scores`), aussi dans `GET /api/leads` : un même lead a la même
  chaleur sur toutes les pages (test d'égalité).
- La même arithmétique entière tourne en Python (`services/outreach_os/heat.py`) et en SQL (`repositories/heat_sql.py`) pour trier ; un test
  les compare sur 37 combinaisons de champs × 6 scores.
- Où : `GET /api/leads` (tri `heat` par défaut, `recent` possible), `GET /api/prospects` (`order=heat|score|recent`), `GET /api/prospects/queues`
  (nombre de hot/warm/cold **comptés** par le serveur), liste des prospects de la carte, file de revue, page Leads.
- « Temps réel » : sans WebSocket (hébergement gratuit), les pages Leads et Review queue **interrogent l'API toutes les 15 s** tant que l'onglet est
  visible, signalent les nouveaux lignes (« new ») et gardent les dernières données si un rafraîchissement échoue. La fiche en cours de revue ne
  change pas sous vos yeux : les nouveaux arrivants rejoignent les files et « Up next ».
