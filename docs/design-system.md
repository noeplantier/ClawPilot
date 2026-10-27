# Design system : le prolongement de plantiers.com

Plantiers - OutreachOS est la version « prospection » de plantiers.com : même identité, mêmes tokens, même logo. La référence est le code de
`noeplantier/PortfolioDev` (`src/lib/tokens.ts`, `src/index.css`, `src/components/ui/*`). Les sites `plantiers.com` / `kretopia.com` n'étaient pas
joignables depuis l'environnement de développement : le design vient du dépôt, pas d'une capture du site en ligne.

## Tokens (une seule source : `frontend/src/index.css` et `frontend/tailwind.config.js`)
| Rôle | Valeur | Utilisation |
|---|---|---|
| Fond « void » | `#07060B` (élevé `#0C0A14`, surface `#120F1E`) | page, barre latérale, panneaux ; `grid-bg` ajoute deux champs violets, un champ vert très léger et une grille fine (statiques, sans filtre ni animation) |
| Violet de marque | `#7C3AED` (hover `#8B5CF6`, lilas `#B79BFF`) | bouton principal en dégradé + halo, kickers `// section`, liens, focus |
| Vert feuille | `#4ADE80` | uniquement l'indicateur « live » |
| Texte | blanc à 95 % / 72 % (`text-soft`) / 58 % (`text-faint`) | `text-foreground`, `text-soft`, `text-faint` : mêmes opacités que le site |
| Cartes | `.surface` (verre sombre, bord `rgba(255,255,255,.08)`, rayon 1 rem), `.glass` pour les panneaux flottants | `bg-card` pour tout ce qui doit être opaque (menus, fenêtres) |
| Typographie | Inter (400-800) + JetBrains Mono (400-600), **auto-hébergées** (`@fontsource`, sous-ensemble latin : accents français inclus) | plus aucune feuille de style tierce bloquante |
| Composants | `.btn-primary` (dégradé violet), `.btn-ghost` / `.btn-ink` (verre), `.btn-purple`, `.btn-danger`, `.chip*` (pastilles mono), `.neo-input`, `.mono-accent` (kicker), `.gradient-word` (mot en dégradé) | |

## Logo
`frontend/src/assets/logo-mark.png` (le « P » ruban + pousse de feuilles, celui du site) via `components/Logo.jsx` : `LogoMark` seul, ou `Logo`
(marque + `PLANTIERS` + sous-ligne mono `OUTREACHOS`, comme « SOFTWARE ENGINEERING » sur le site). Utilisé dans la barre latérale (repliée : la marque seule),
l'en-tête mobile, l'écran de démarrage, la connexion et l'inscription. Favicons, `apple-touch-icon`, icônes du manifeste et image de partage
(`og-image.jpg`) sont ceux du site ; `theme-color` = `#07060B`.

## Règles
- Un écran n'écrit **aucune couleur** dans un nom de classe (`text-[#…]`, `bg-[#…]`) ni de gris Tailwind : il utilise les tokens ci-dessus. `src/theme.test.js` le vérifie.
- Les couleurs de données (graphiques, étapes du pipeline, pastilles) viennent de la palette violet / vert / ambre / rouge, lisibles sur fond sombre.
- La carte garde le fond OpenStreetMap standard (décision du produit) ; seuls ses panneaux, fenêtres et pastilles suivent le thème.
- Mouvement : transitions de 200-300 ms sur la couleur, la bordure et l'ombre ; `prefers-reduced-motion` coupe les animations.
