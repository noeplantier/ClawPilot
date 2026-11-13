# Design system : le prolongement de plantiers.com

Plantiers - OutreachOS est la version « prospection » de plantiers.com : même identité, mêmes tokens, même logo. La référence est le code de
`noeplantier/PortfolioDev` (`src/lib/tokens.ts`, `src/index.css`, `src/components/ui/*`). Les sites `plantiers.com` / `kretopia.com` n'étaient pas
joignables depuis l'environnement de développement : le design vient du dépôt, pas d'une capture du site en ligne.

## Tokens (une seule source : `frontend/src/index.css` et `frontend/tailwind.config.js`)
| Rôle | Valeur | Utilisation |
|---|---|---|
| Fond « void » | `#07060B` (élevé `#0C0A14`, surface `#120F1E`) | page, barre latérale, panneaux ; `grid-bg` ajoute deux champs violets, un champ vert très léger et une grille fine (statiques, sans filtre ni animation) |
| Violet de marque | `#7C3AED` (brand-500 ; brand-400 `#9B74FA` au survol et au focus, lilas / brand-300 `#B79BFF`) | bouton principal plein + halo, kickers `// section`, liens, focus |
| Vert feuille | `#4ADE80` | uniquement l'indicateur « live » |
| Texte | blanc à 95 % / 72 % (`text-soft`) / 58 % (`text-faint`) | `text-foreground`, `text-soft`, `text-faint` : mêmes opacités que le site |
| Cartes | `.surface` (verre sombre, bord `rgba(255,255,255,.08)`, rayon 1 rem), `.glass` pour les panneaux flottants | `bg-card` pour tout ce qui doit être opaque (menus, fenêtres) |
| Typographie | Inter (400-800) + JetBrains Mono (400-600), **auto-hébergées** (`@fontsource`, sous-ensemble latin : accents français inclus) | plus aucune feuille de style tierce bloquante |
| Composants | `.btn-primary` (violet plein, bord haut clair + halo, se soulève de 2 px au survol), `.btn-ghost` / `.btn-ink` (verre), `.btn-purple`, `.btn-danger`, `.chip*` (pastilles mono), `.neo-input`, `.mono-accent` (kicker), `.gradient-word` (mot en dégradé) | |

## Surtitres, titres et cartes (alignés sur le site, commit `10dcb5d` de `noeplantier/plantiers`)
- **Surtitre** `.eyebrow` : trait de 2 rem en dégradé vers `brand-500`, puis le libellé en JetBrains Mono 10 px, capitales, espacement 0,3 em, `brand-400`
  (comme `SectionHeading` du site). Il remplace l'ancien « // section » dans les en-têtes de page et les cartes (`Widget`).
- **Titre de page** : `font-bold`, interlignage 1,15 (le `WordReveal` du site), plus de `font-black`.
- **Lueur des cartes** : une lumière violette douce suit le pointeur sur toute `.surface` (le `glow` du `Card` du site), posée par `lib/cardGlow.js`
  (variables CSS `--mx` / `--my`, un seul écouteur, aucun état React) ; coupée sous `prefers-reduced-motion`.

## Pages fusionnées
Une entrée de la barre latérale peut porter plusieurs écrans (`also` dans `lib/sections.js`) : chaque écran garde son chemin, la page affiche un seul titre
et une rangée d'onglets (`components/shell/HubTabs.jsx`, compteurs lus sur l'API, rien quand l'API ne répond pas).
- **Outreach › Campagnes** (`/app/campaigns`, `/app/journey`, `/app/launch`) : chiffres et graphiques en direct (`GET /dashboard/overview`, toutes les 10 s), puis
  Par zone · Individuelle · Séquences.
- **Leads › À traiter** (`/app/prospects/review`, `/app/prospects/to-enrich`) : la sélection automatique du serveur (approuvée en un clic), puis À vérifier · À enrichir.
- **Pilotage › Automatisations** (`/app/automation-max`, `/app/agents`) : Mandat · Agents.
- **CRM / Pipeline** : la même barre que Prospects (actions secondaires en verre, une seule action principale, onglets CRM · Pipeline · Map).

## Logo
`frontend/src/assets/logo-mark.png` (le « P » ruban + pousse de feuilles, celui du site) via `components/Logo.jsx` : `LogoMark` seul, ou `Logo`
(marque + `PLANTIERS` + sous-ligne mono `OUTREACHOS`, comme « SOFTWARE ENGINEERING » sur le site). Utilisé dans la barre latérale (repliée : la marque seule),
l'en-tête mobile, l'écran de démarrage, la connexion et l'inscription. Favicons, `apple-touch-icon`, icônes du manifeste et image de partage
(`og-image.jpg`) sont ceux du site ; `theme-color` = `#07060B`.

## Règles
- Un écran n'écrit **aucune couleur** dans un nom de classe (`text-[#…]`, `bg-[#…]`) ni de gris Tailwind : il utilise les tokens ci-dessus. `src/theme.test.js` le vérifie.
- Les couleurs de données (graphiques, étapes du pipeline, pastilles) viennent de la palette violet / vert / ambre / rouge, lisibles sur fond sombre.
- La carte garde les tuiles OpenStreetMap standard (décision du produit : une source, une attribution, aucune clé) ; son look « nuit » est un filtre CSS sur ces tuiles
  (`.map-stage`, `index.css`), désactivable par le bouton soleil/lune (« Classic map », préférence mémorisée). Voir « Carte futuriste » plus bas.
- Mouvement : transitions de 200-300 ms sur la couleur, la bordure et l'ombre ; `prefers-reduced-motion` coupe les animations.


## Référence lue (lecture seule) et écarts mesurés
Source : `noeplantier/plantiers` (le code de plantiers.com), commit `10dcb5d` : `src/lib/tokens.ts`, `tailwind.config.js`, `src/index.css`,
`src/components/ui/Button.tsx`. Rien n'en est importé (ni script, ni dépendance, ni infrastructure) : les valeurs utiles sont copiées dans
`frontend/src/design/plantiers-reference.json` et **`src/designTokens.test.js` vérifie que notre feuille de style les porte exactement**.
Limite : le site déployé lui-même n'est pas joignable depuis la machine de travail ; seul son code source a été lu, pas son rendu.

| Élément | Site | Ce produit avant | Maintenant |
|---|---|---|---|
| Couleurs (void, brand, leaf), ombres de halo, opacités du texte, Inter + JetBrains Mono | `tokens.ts` | identiques | identiques (testé) |
| Anneau de focus | `ring-2 ring-brand-400 ring-offset-2` | outline lilas (`#B79BFF`) | outline brand-400 (`#9B74FA`), 2 px, décalé de 2 px |
| Bouton principal | `bg-brand-500` plein, bord haut `inset 0 1px 0 rgba(255,255,255,.35)`, halo `0 8px 24px -6px`, survol : −2 px, `bg-brand-400`, halo `0 14px 40px -8px`, pression `scale(.97)` | dégradé animé (`background-position`) | comme le site (transform et ombre seulement) |
| Bouton secondaire | `bg-white/[.04] border-white/[.1]`, survol `bg-white/[.08] border-white/20` | idem à 2 points d'opacité près | bord de survol à `.20` |
| Mouvement | transform / opacité seulement, boucles coupées sous `prefers-reduced-motion` | idem sauf le survol du bouton | survol et pression coupés sous `prefers-reduced-motion` ; aucune boucle sur la carte ni les tableaux |

Non repris volontairement (identité de la vitrine, pas d'un outil de travail) : l'aurore animée, le sol 3D, les lueurs qui suivent le curseur, la
palette de commandes, la barre de défilement. Un seul bouton principal par écran.

## Coque : six rubriques
La barre latérale n'a que six entrées, à plat : Vue d'ensemble, Prospection, Leads, Batches, Outreach, Pilotage (`lib/sections.js`, une seule source).
Pas d'arbre : ce qui vivait en sous-entrées est la rangée d'**onglets** en haut du contenu (`SectionTabs` dans `Layout`), avec le Composer IA. Le compte
(organisation, e-mail, déconnexion) est le pied de la barre, pas une septième entrée. Toutes les routes existantes sont conservées ; `sections.test.js`
vérifie que chaque écran de `App.js` appartient à une rubrique et que chaque onglet mène à un écran qui existe.
- Hauteur : les six liens et le pied tiennent sans défilement de 1440×900 à 1024×480 (`e2e/navigation.spec.js`) ; sous 620 px de haut le bloc compte se réduit
  et les liens se resserrent ; la liste garde `overflow-y: auto` en filet de sécurité, jamais `hidden`.
- Mobile : tiroir modal, piège de focus, Échap, focus rendu au bouton « Menu » ; les onglets défilent horizontalement, aucun n'est coupé.
- Connexion et inscription partagent `AuthShell` : carte centrée dans la hauteur libre, page qui défile quand l'écran est court ou que le clavier mobile en prend la moitié
  (`100dvh`), aucun statut serveur affiché (la page ne peut pas le connaître), champs `username` / `current-password` / `new-password` pour les gestionnaires de mots de passe.
- « Batches » = l'historique réel (recherches de carte, imports) et l'avancement des brouillons ; **aucun préréglage ni pause/reprise** : aucun moteur serveur ne les porte
  (`ProspectingBatch` n'a que des modèles, sans route), donc rien n'est simulé.

## Carte futuriste
`pages/MapSearch.jsx`, styles `.map-*` de `index.css`. Rien n'y porte une couleur de son propre chef : tout vient des jetons (`--void`, `--brand-*`, `--leaf`, `--accent-warning`).
- **Fond nuit** : filtre sur le panneau de tuiles (inversion, teintes remises à l'endroit, désaturé, éclairci) : parcs verts, eau bleue, étiquettes claires, routes lisibles.
  Vignette violette, grain fin et quatre équerres (décor `aria-hidden`). « Classic map » les retire.
- **Pastilles** : losange = prospect qualifié, rond = lieu trouvé par la recherche ; la couleur garde son sens (contact publié, statut de revue), la lueur est dans la teinte.
  Anneau doré = intention observée **et sourcée** (jamais un score) ; anneau cyan = nouveau. Les anneaux pulsent 3 fois puis se figent ; rien ne tourne en boucle sur la carte,
  sauf le **balayage radar** pendant qu'une requête OpenStreetMap est réellement en cours (et sa pastille dans le HUD) : ils disparaissent avec la requête et s'arrêtent sous
  `prefers-reduced-motion` (`designTokens.test.js` le vérifie).
- **HUD** (`MapHud`, `lib/mapHud.js`, ≥ 1024 px) : centre de la vue, zoom, et l'état de la zone (prêt / trop large / balayage). Chaque valeur est lue de la carte ou de la recherche ;
  aucun chiffre inventé.
- **Hauteur** : sur ordinateur la carte remplit `<main>` (`md:h-full`) : la barre de rubriques et le pied n'en retirent plus une valeur codée en dur ; les contrôles de zoom ne passent plus sous le pied.
