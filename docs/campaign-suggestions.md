# Suggestions de campagnes en temps réel

Page **Campaigns** : un panneau « Suggested campaigns » se recalcule **toutes les 15 s** (onglet visible) à partir de **vos** leads CRM et
prospects. Aucun modèle de langage, aucune donnée inventée : une suggestion est un **groupe de personnes qui partagent quelque chose de
réellement enregistré**, avec des chiffres comptés.

## D'où viennent les suggestions (`services/outreach_os/suggestions.py`, pur et testé)
| Type | Groupe | Exemple de titre |
|---|---|---|
| `segment` | prospects d'une même catégorie **connue** et d'une même ville **connue** (≥ 2) | « Bakery in Lyon » |
| `signal` | prospects chez qui un signal est **détecté** sur leurs propres pages (≥ 2) ; un signal « inconnu » ou rejeté par un relecteur ne compte pas | « No own website listed » + angle « Offer: a first website » |
| `hot` | contacts **chauds** (voir `docs/scoring.md`) avec e-mail ou téléphone connu | « Your hottest reachable contacts » |
| `new_leads` | leads CRM au stade `new` avec un contact connu | « New leads still waiting for a first message » |

Un prospect refusé n'est jamais suggéré. Chaque suggestion affiche : le nombre de personnes, combien sont chaudes, combien ont un e-mail /
un téléphone **connus**, la chaleur moyenne des plus chaudes, trois exemples, et **combien peuvent rejoindre une campagne aujourd'hui**.
Classement : chaleur des plus chaudes membres + taille du groupe (plafonnée), 8 suggestions au plus.

## Ce qui bloque, dit clairement
Les règles d'envoi s'appliquent : un prospect de la découverte n'est joignable qu'approuvé **et** avec l'envoi réel activé. Sinon la carte affiche
la raison (« Live sending is off (dry-run) », « N prospects wait for approval in the review queue »…) et le bouton reste « NOT READY » : aucun bouton mort.

## Créer
`POST /api/campaigns/suggestions/{id}/create` crée un **brouillon** (sans étape) et y affecte les personnes éligibles, par la même porte que
`assign-leads` ; journalisé (`campaign.suggestion_created`) ; 10 créations par minute et par organisation. **Rien n'est envoyé** : on ajoute des
étapes puis on lance, le consentement et les limites d'envoi s'appliquent à chaque message. Si aucune personne n'est éligible : `409` avec la raison
et aucune campagne vide n'est laissée.

## Limites
Polling (pas de WebSocket sur l'hébergement gratuit). Les groupes se forment sur les champs connus : plus vos données sont riches (ville, catégorie,
signaux), plus les suggestions sont précises. Le contenu des messages n'est pas généré ici.
