# Automatisation max : un mandat explicite et borné

**Désactivé par défaut. Non activé en production par cette livraison.** API : `/api/mandates` (`routes/mandates.py`). Écran : **Pilotage › Automatisation max**
(`/app/automation-max`, livré avec la tranche interface). Le mode laisse le système envoyer, dans des limites écrites à l'avance, sans qu'une personne valide chaque
message. Ce n'est pas un mode « tout automatique » : il n'élargit jamais rien tout seul.

## Interrupteur serveur

`FEATURE_AUTOMATION_MAX=true` (variable du serveur, `backend/.env.example`) rend le mode **disponible**. Sans elle, l'activation d'un
mandat est refusée (403 `feature_disabled`) et l'écran le dit, en nommant la variable. L'application ne peut pas activer ce mode
elle-même : c'est une décision de l'opérateur du serveur. Disponible ne veut pas dire actif : rien n'agit sans mandat autorisé.

## Le mandat : une autorisation unique, bornée

Un mandat se crée en **brouillon** (il n'agit pas) à partir d'une campagne par zone, avec :

| Borne | Valeur |
|---|---|
| Zone(s) | celles de la campagne, au plus `MAX_ZONES` (1) ; jamais élargies automatiquement |
| Offre, modèle, version | celles de la campagne au moment de l'autorisation |
| Expéditeur et fournisseur | ceux du serveur au moment de l'autorisation |
| Plafond par jour, plafond total | entiers bornés par le serveur (`MAX_DAILY` ≤ `MAX_TOTAL`, 100 messages au plus) |
| Expiration | un nombre de jours (`MAX_DAYS`) : un mandat ne dure pas indéfiniment |
| Cadence | délai minimal entre deux messages, fenêtre horaire d'envoi |
| Fréquence de recherche | au moins `MIN_SEARCH_HOURS` ; le mandat traite les établissements de la zone, la découverte n'est pas automatique |
| Budget IA | 0 par défaut : le message est le modèle approuvé, rendu sans IA |
| Arrêts configurables | taux de rebonds (≤ 10 %), taux d'oppositions (≤ 20 %), échantillon minimal |

Un seul mandat actif par compte.

## L'autorisation explicite

Activer demande, **par un propriétaire** : les quatre confirmations cochées (par leurs codes) — le mandat n'agit que dans ses bornes ·
les messages partent pour de vrai quand l'envoi réel est activé · les conditions du fournisseur et la loi sur la prospection sont deux
vérifications distinctes, faites · la révocation est possible à tout instant mais ce qui est parti ne se rappelle pas. Le serveur refuse
aussi si : le mode n'est pas disponible, les réponses ne sont pas lues (IMAP + worker), la configuration est incomplète, la campagne n'est
pas approuvée. Le refus est écrit dans le journal **avant** de répondre en erreur.

## Ce qui arrête le mandat

**Fixes, non désactivables** : arrêt d'urgence (`SEND_KILL_SWITCH` : le mandat est retenu, rien ne part, sans être terminé), erreur d'authentification du serveur de messagerie, réponses non
lues, changement du modèle, de la zone, de l'offre, de l'expéditeur ou du fournisseur (revalidation requise), expiration, plafond total.
**Configurables dans les bornes** : taux de rebonds et d'oppositions. Chaque tour revérifie tout ; un arrêt est un état visible avec sa
raison dans le journal, jamais un échec silencieux. Chaque message passe en plus **toutes** les portes habituelles du moteur d'envoi.

## Pause, révocation, revalidation

- **Pause** : rien ne part, le plan reste ; l'activation reprend (avec les quatre confirmations).
- **Révocation** : immédiate et définitive, quel que soit l'état de l'interrupteur serveur ; les envois planifiés sont annulés et les
  approbations retirées.
- **Revalidation** : après un changement substantiel, une personne relit et ré-épingle le mandat à ce qui est vrai maintenant, puis
  l'autorise de nouveau.

## Journal et rapport

Journal append-only (`mandate_events`) : création, autorisation, pauses, arrêts, tours, refus, revalidations, avec l'auteur
(personne ou automatique). `GET /api/mandates/{id}/report` : envoyés sur 24 h et au total, ce qu'il reste des plafonds et des jours, la
progression de la campagne et le journal. Le rapport rappelle que le mode n'a rien élargi.

## Conformité

La conformité juridique (consentement, désinscription, identité, origine des données, droit applicable) et les conditions du
fournisseur d'envoi sont **deux contrôles séparés**. Hostinger, par exemple, interdit l'envoi de masse non sollicité depuis sa
messagerie mutualisée : sous ce fournisseur, seul un opt-in explicite (ou une base « consentement » déclarée) autorise une campagne, et
un quota disponible ne vaut jamais autorisation. L'application applique ces politiques ; elle ne remplace ni votre relecture des conditions
ni un avis juridique.

## Vérifier localement (sans rien envoyer)

```bash
cd backend && pytest tests/unit/test_mandate_rules.py
uvicorn server:app --port 8000 &
REACT_APP_BACKEND_URL=http://localhost:8000 pytest tests/test_mandate.py -v
cd ../frontend && npm test -- --watchAll=false src/pages/automationMax.test.jsx src/lib/mandateFormat.test.js
```

## Limites connues

- Pas de découverte automatique de nouveaux établissements dans le mandat : une zone, au plus 100 messages.
- Le mode exige l'interrupteur serveur, la lecture des réponses (IMAP) et un worker avec son beat (`EMBEDDED_WORKER=1` ou services dédiés).
- Aucune notification externe n'est envoyée ; le rapport se lit dans l'écran.

## Pilote automatique (en amont du mandat)

**Désactivé par défaut.** Écran : **Pilotage › Automatisations** (en tête). API : `/api/autopilot` (`routes/autopilot.py`), règles pures
`services/outreach_os/autopilot.py`, exécution `services/autopilot_runner.py`, tâche `tasks.autopilot_tasks.run_autopilots` (toutes les 15 min).

Un **propriétaire** l'active avec quatre confirmations (`b2b_use`, `auto_approve`, `ai_credits`, `can_stop`). À chaque passage (planifié, ou
« Lancer maintenant ») il fait, dans cet ordre et seulement ce qui a été autorisé :

1. **Recherche** de la zone sur la carte, au plus toutes les `MIN_SEARCH_HOURS` (6 h), par le même job persisté que l'écran Carte (Overpass,
   cache, limites). Exige `FEATURE_EXTERNAL_SOURCES` ; sinon la recherche est sautée et le passage le dit.
2. **Ajout** des lieux qui ont publié un téléphone **et** un e-mail, par le même import attesté que l'ajout groupé de la carte (origine OSM, base
   légale, liste d'opposition), en attente de relecture. Exige `FEATURE_PROSPECT_IMPORT`.
3. **Approbation** des prospects en attente que la politique d'éligibilité qualifie, au plus `max_approvals` (≤ 200) par passage, au nom du
   propriétaire, chaque décision écrite dans le journal (`via: auto_selection`).
4. **Brouillons IA** des prospects approuvés à ce passage, dans la limite des crédits.

Il **n'envoie jamais** : l'envoi reste au mandat actif, dans ses plafonds, par toutes les portes du moteur d'envoi. Un passage est écrit dans le
journal d'audit (`autopilot.run`) avec ce qu'il a fait et sauté. Arrêt à tout instant par un propriétaire ou un administrateur ; le pilote
s'arrête aussi seul si le propriétaire qui l'a autorisé n'est plus propriétaire du compte.
