# Temps de chargement

## Ce qui rendait les pages lentes
L'API tourne sur une instance Render **gratuite** : sans trafic pendant 15 minutes, elle s'endort, et la première requête suivante attend
environ une minute qu'elle se réveille. Jusqu'ici l'interface attendait cette réponse (`/auth/me`) avant d'afficher quoi que ce soit, puis
chaque page repartait d'un écran vide. Le reste (hébergement statique Netlify, bundle de 183 Ko compressés) était déjà rapide.

## Ce qui a été fait (sans rien payer)
| Levier | Où | Effet |
|---|---|---|
| Réveil de l'API pendant le chargement des scripts | `frontend/public/index.html` (préconnexion + `GET /api/health`) | La première requête trouve l'API réveillée |
| Ping toutes les 10 min | `.github/workflows/keepalive.yml` (gratuit : dépôt public) | L'API ne s'endort plus |
| Démarrage instantané d'une session ouverte | `AuthContext` garde l'identité (`outreachos_session`) | L'application s'affiche tout de suite, le serveur confirme ensuite. Seul un 401 ferme la session (un serveur injoignable ne déconnecte plus) |
| Dernière réponse affichée tout de suite | `lib/swr.js` + option `key` de `useAsync` / `useLive` | Une page déjà vue ou un rechargement n'est jamais vide ; la réponse du serveur remplace la copie. Mémoire + `sessionStorage` (fermer l'onglet l'efface) ; vidé à la déconnexion et sur 401 |
| Données en temps réel | option `intervalMs` (15 s) : Tableau de bord, Prospects, Campagnes, Messages, Analytics, Sending, File de relecture, Leads, Santé, Réglages, carte | Rafraîchi tant que l'onglet est visible, et **immédiatement** au retour sur l'onglet. Un rafraîchissement qui échoue garde ce qui est affiché et le dit |
| Écrans préchargés | `lib/routes.js` : au survol/focus d'un lien, puis tous les écrans quand le navigateur est inactif (sauf « économiser les données ») | Ouvrir un écran est instantané |
| Plus d'apparition en fondu entre deux écrans | `Layout.jsx` | Le contenu est visible dès qu'il est prêt |
| Compositeur IA chargé à l'ouverture seulement | `Layout.jsx` | Bundle initial plus léger |
| Réponses de l'API compressées (gzip, ≥ 1 Ko) | `backend/server.py` | Une liste de leads pèse environ dix fois moins sur le réseau |

## À faire côté Render (hors code)
- **Supprimer l'ancien service Node « ClawPilot »** : deux services gratuits allumés en permanence dépassent les 750 heures mensuelles
  offertes et Render les suspend en fin de mois. Un seul service (`clawpilot-api`) tient dans le quota.
- Définir le **Health Check Path** de `clawpilot-api` sur `/api/health` (Settings > Health & Alerts).
- Facultatif : variable de dépôt GitHub `API_HEALTH_URL` si l'adresse de l'API change.

## Vérifier
- `npm test` : `swr`, `useAsync` (cache, interrogation, onglet masqué), `auth`, `routes`.
- Playwright : « a returning visitor sees the app and the last data at once, even while the API is still waking up » (l'API répond en 5 s,
  l'application et le dernier tableau de bord sont affichés en moins de 4 s) et « signing out leaves nothing of the organisation in the browser ».
- `curl -sI -H 'Accept-Encoding: gzip' https://clawpilot-api.onrender.com/openapi.json` : `content-encoding: gzip`.


## Carte : le retard d'environ deux minutes, mesuré
Chaîne : action → API → (file) → découverte → enrichissement → qualification → persistance → sondage → marqueur. Fournisseur Overpass **factice** local
(`measure` : un serveur muet + un serveur rapide à 0,3 s) ; PostgreSQL 16 local, même machine, aucune latence réseau. Le temps du fournisseur réel
n'est pas mesurable d'ici (pas d'accès réseau aux serveurs Overpass) ni sur Render (les métriques HTTP du service sont vides).

| Étape | Avant | Après |
|---|---|---|
| Découverte Celery (`tasks/prospecting_tasks`), 1 serveur muet | **73,1 s** (2 × 35 s + pauses) | ≤ 15 s une fois, puis ~0,3 s (cooldown) |
| Découverte Celery, 2 serveurs muets | ≈ 2 min 25 s (calculé) | ≤ 30 s une fois |
| Recherche `/map/search`, 1 serveur muet | 15,4 s puis cache 28 ms | inchangé (déjà le client partagé) |
| Lieu complet ajouté → présent sur la carte | **jamais** (score 10, « pas hot », rien ne re-score) | au prochain sondage (≤ 2 s en rafale) |
| Rythme de sondage | 20 s fixes | ~10 s, ~2 s pendant 2 min après une action, 0 en arrière-plan |

Cause du retard : la découverte Celery avait **sa propre liste de serveurs** (3 en dur), 35 s par requête, 2 essais par serveur et aucune mémoire d'un
serveur tombé ; un serveur muet la retenait 73 s. Et **en production il n'y a aucun worker Celery ni Beat** (un seul service web `clawpilot-api`,
`start.sh` = uvicorn) : ce chemin n'avance pas sans worker. Le chemin réellement utilisé par la page (`/map/search`) tourne dans le processus de l'API.

Volume 2 000 prospects dont 400 incomplets (1 600 dessinés), 50 requêtes, local :

| Endpoint | Avant (p50 / p95) | Après, données inchangées (p50 / p95) |
|---|---|---|
| `GET /map/prospects` | 544 / 696 ms (le 304 coûtait pareil) | **36 / 40 ms** ; **9 / 11 ms** en 304 |
| `GET /map/cities` | 330 / 400 ms | 9 / 12 ms |
| `GET /suggestions/focus` | 689 / 780 ms | 9 / 11 ms |
| `GET /prospects/to-enrich` | 576 / 991 ms | mis en cache de la même façon |
| Premier calcul après un changement | — | ≈ 290 ms (prédicat de qualification ≈ 180 ms, dont suppression ≈ 110 ms) |

Un jeton de changement (`prospect_repo.change_token`, sept agrégats indexés, une requête) décide si la dernière réponse est encore valable ; l'heure
en fait partie (les fenêtres de fraîcheur sont en jours). Les chiffres d'une instance Render gratuite (0,1 CPU) seront plus élevés : à mesurer après
déploiement avec `docs/performance.md` § Vérifier.
