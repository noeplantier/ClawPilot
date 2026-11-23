# Éligibilité, Hot et brouillons automatiques

## Une seule décision
`services/outreach_os/eligibility.py` (pur, `now` injecté) et son jumeau SQL `repositories/eligibility_sql.py` décident de la même façon, et
`tests/test_eligibility_parity.py` le prouve sur 40 cas stockés dans PostgreSQL (suppression par e-mail / téléphone / domaine, E.164, JSON mal
formé, point (0,0), fraîcheur, comparaison « qualifié OU non qualifié » pour qu'aucun NULL ne fasse disparaître un prospect). La carte, la file
« To enrich », les compteurs par ville, `/suggestions/focus` et les candidats aux brouillons lisent cette décision ; aucune page ne la recalcule.

| | Règle |
|---|---|
| Identité | un nom réel (pas vide / `unknown`) |
| E-mail | syntaxe valide (`normalize_email`), pas un domaine réservé (`example`, `invalid`, `test`, `localhost`) |
| Téléphone | normalisable en E.164 (`normalize_phone`) |
| Adresse + position | sur la dernière source **non démo** : adresse ≥ 5 caractères, latitude/longitude numériques, dans l'intervalle, pas (0, 0) |
| Provenance | source identifiable, `fetched_at` ≤ `OUTREACH_SOURCE_TTL_DAYS` (30) |
| Fit | `Lead.fit_score` ≥ `OUTREACH_MIN_FIT_SCORE` (60), calculé depuis ≤ `OUTREACH_FIT_TTL_DAYS` (30) |
| Exclus (pas « à enrichir ») | rejeté, supprimé (e-mail / téléphone / domaine du site), opposition e-mail, source ou consentement de démonstration |
| **Facultatifs** | site web, WhatsApp. Un téléphone ne prouve pas WhatsApp ; une syntaxe d'e-mail ne prouve pas la boîte |

**Qualifié prioritaire** = ces critères. **Hot** = qualifié **et** un signal `commercial_intent` détecté, avec preuve, récent
(`OUTREACH_INTENT_TTL_DAYS`), rattaché à une source réelle du même prospect. Les signaux de besoin (pas de site, pas de réservation…) ne sont pas
une intention d'achat : aucun producteur d'intention n'existe aujourd'hui, donc **Hot est vide** et l'interface le dit (« none hot: no commercial
intent observed »). Rien ne fabrique une intention pour remplir la carte.

Le score de fit (`services/qualification_scoring`, existant) est calculé **dans la requête qui enregistre le prospect** (`prospect_repo.score_fit`,
appelé par `pipeline._ingest`), avec ou sans site : plus aucun worker ni Beat à attendre. Ce n'est pas un modèle d'ICP : c'est un indicateur de
complétude du profil et de la page lue, à poids fixes. `website_quality` d'un prospect sans site reflète ses coordonnées, pas un site.

## File « To enrich »
`GET /api/prospects/to-enrich` (pagination serveur) liste les prospects ni qualifiés ni exclus, avec `missing_fields`
(`name_missing`, `email_missing|invalid`, `phone_missing|invalid`, `address_missing`, `coordinates_missing`, `source_missing|stale`,
`fit_missing|stale|low`). Ils restent, ne sont pas contactables par défaut, et ne sont pas sur la carte.

## Brouillons IA automatiques
Déclencheurs (jamais au rendu d'un composant) : un import, un ajout depuis la carte, l'enregistrement de l'offre, `POST /prospects/draft-jobs/run`.
`services/draft_runner.py` tourne dans le processus de l'API (comme `map_job_runner`) : pas de worker à ajouter.

- **Offre** (`accounts.offer`, `GET/PUT /api/settings/offer`, page `/app/settings/offer`) : sans offre complète, le statut est `offer_required` et rien n'est inventé.
- **Tâche** `draft_jobs` : `queued → generating → ready | failed | unavailable`. Une clé d'idempotence par compte + prospect + canal + offre + langue + version de
  gabarit + empreinte des données utiles : un rafraîchissement ou un second balayage ne génère rien de plus ; un brouillon édité ou validé n'est jamais écrasé.
- **Bornes** : 40 prospects examinés, 10 brouillons, 2 en parallèle par balayage ; une limite du fournisseur arrête le balayage, la reprise a lieu au balayage suivant
  (`unavailable` : 5 min, `failed` : 2 min, 3 essais). Le fournisseur est celui de `ai_svc` (Groq si configuré) ; aucun fournisseur payant ajouté.
- **Présence Web, dite comme elle est connue** : `site_found` / `site_unreachable` / `none_identified` (l'annuaire lu n'en porte pas : « Je n'ai pas identifié de site
  officiel pour votre établissement. ») / `unknown` (aucune affirmation). Un champ vide ne devient jamais « vous n'avez pas de site ». Aucune affirmation de lenteur ou de
  mauvais référencement. La réponse est contrôlée (chiffre, lien, contact, affirmation non mesurée, « vous n'avez pas de site ») et **écartée** au moindre doute.
- Les faits envoyés au fournisseur : nom, activité, ville, observations avec preuve, offre. Jamais l'e-mail ni le téléphone. Le contenu d'un site est une donnée, pas une instruction.
- Le brouillon est créé en `draft` (jamais approuvé), avec le pied de page obligatoire (identité, origine des données, lien de désinscription). **Aucun envoi.**


## Sélection automatique (`routes/auto_selection.py`)
`GET /api/prospects/auto/selection` liste les prospects **en attente de relecture** que cette même politique qualifie, le plus chaud d'abord
(`prospect_repo.list_positions(review_status="pending")`). `POST /api/prospects/auto/review` (propriétaire ou administrateur, 500 au plus) applique la décision
de la personne à toute la sélection : seuls les prospects encore `pending` sont décidés, la liste d'opposition est vérifiée pour chacun, chaque décision est
écrite dans le journal d'audit (`via: auto_selection`). Rien n'est envoyé.
