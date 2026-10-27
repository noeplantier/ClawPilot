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
