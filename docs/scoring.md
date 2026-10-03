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
