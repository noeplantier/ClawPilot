# Conformité

Ce document décrit ce que le code fait réellement. Il ne remplace pas un avis juridique (RGPD, ePrivacy/LCEN, règles des
fournisseurs). Les points à valider avec un juriste sont marqués **[à valider]**.

## Principes appliqués

| Exigence | Mise en œuvre |
|---|---|
| Sources autorisées uniquement | Seule une source locale fictive est implémentée. Les sources réseau sont derrière `FEATURE_EXTERNAL_SOURCES` (inexistant, éteint). Avant d'en écrire une : lire ses CGU et son `robots.txt`, pas de contournement de CAPTCHA, de login, de paywall ni de limite de débit. |
| Pas de LinkedIn | Aucun code, aucune extension, aucun navigateur automatisé. |
| Pas d'invention | Un brouillon n'énonce que des faits portés par un signal `detected` avec preuve. Sans fait exploitable : introduction neutre. |
| Provenance | Chaque prospect garde ses sources (nom, URL, date, hash du contenu, note de licence). |
| Humain dans la boucle | Un prospect doit être **approuvé** par un `owner`/`admin`, puis chaque brouillon aussi. Chaque décision est dans `audit_logs`. |
| Consentement | E-mail : bloqué seulement si `opted_out` (règle projet). WhatsApp : opt-in explicite, jamais utilisé ici. Passage par `consent_repo.can_send`. **[à valider]** la base « intérêt légitime B2B » et la prospection d'entrepreneurs individuels (qui peuvent être des personnes physiques). |
| Identité de l'expéditeur | `OUTREACH_SENDER_NAME/COMPANY/ADDRESS/EMAIL` obligatoires, jamais de valeur par défaut : sans eux, pas de brouillon. |
| Origine des données | Phrase obligatoire dans chaque brouillon (« vos coordonnées figurent dans l'annuaire … »). |
| Désinscription | Lien signé (HMAC) dans chaque brouillon vers `/api/unsubscribe/{token}` (public, idempotent). Il suspend immédiatement l'e-mail, le téléphone et le domaine de l'organisation et enregistre un opt-out. L'approbation d'un brouillon est refusée si l'un de ces éléments manque. |
| Droit à l'effacement | `POST /api/prospects/{id}/erase` : vide les données personnelles partout où elles ont été copiées (lead, contacts, sources, preuves des signaux, détail des scores, brouillons), puis suspend l'identité pour que l'organisation ne la redécouvre pas. |
| Limites d'envoi | Plafond quotidien (20 par défaut), plafond horaire, délai minimum (60 s par défaut), appliqués **avant** l'adaptateur ; dépassement ⇒ 429 avec heure de reprise. Compté dans le fuseau de l'organisation. S'appliquent aussi à l'envoi unitaire, au lot, aux étapes de campagne et aux tâches Celery ; tous les chemins comptent dans les mêmes plafonds (`services/send_gate.py`). |
| Arrêt d'urgence | `SEND_KILL_SWITCH=true` (environnement) refuse tout envoi, y compris les anciens chemins SendGrid et Twilio ; `sending_paused` coupe une organisation, tous canaux et tous chemins confondus. |
| Rebond | Un rebond dur suspend l'adresse (raison `bounce`). |
| Réponse STOP | Une réponse de type STOP/désinscription désinscrit immédiatement (même chemin que le lien). Les autres réponses sont seulement enregistrées (extrait de 500 caractères, effacé avec le prospect). |
| Un brouillon, un message | La même clé d'idempotence, ou un autre identifiant pour le même brouillon, ne produit jamais un second message. |
| Aucun envoi par défaut | `dry_run` actif tant que `FEATURE_LIVE_SENDING` n'est pas explicitement à `true`. L'adaptateur SMTP exige `SMTP_*` complet (sinon 501) et TLS vérifié. |
| Sandbox | Tant que `OUTREACH_SANDBOX` n'est pas mis à `false` explicitement, un envoi réel n'atteint que `OUTREACH_LIVE_ALLOWLIST` (liste vide = personne), vérifié au dispatch **et** dans l'adaptateur. |
| Au plus un envoi | Le message est écrit `sending` et validé avant l'appel SMTP ; une issue inconnue n'est jamais renvoyée seule. |
| Test de connexion | `POST /outbound/test-send` : un message technique (identité imprimée, en-tête `List-Unsubscribe` en `mailto:`), uniquement vers l'adresse de l'expéditeur ou la liste blanche, même limites et kill switch que le reste ; pas d'événement d'outreach, donc pas de KPI faussé. |
| Secrets | Aucun secret dans le code, les tests (valeurs aléatoires par exécution) ni les logs. Les identités suspendues sont stockées en empreintes. |

## Choix à connaître

- **Suppression par organisation, pas inter-organisations.** Chaque organisation est responsable de ses données ; une
  liste commune permettrait à un locataire d'en bloquer un autre. Une liste d'opposition inter-organisations serait un choix produit
  distinct **[à valider]**.
- **Exception à l'append-only.** L'effacement modifie `prospect_sources.fields`, `prospect_signals.evidence`,
  `prospect_scores.breakdown` et `message_drafts` : le droit à l'effacement l'emporte. Les lignes sont conservées (compteurs,
  clés étrangères, audit) mais vidées. `audit_logs` ne contient jamais d'identité ni de texte libre.
- **Désinscription par GET.** Un prefetch de lien par un antivirus peut provoquer une désinscription abusive ; l'erreur va dans le
  sens sûr (ne plus écrire). POST est aussi accepté (RFC 8058).
- **Journal d'envoi non rejouable.** `outbound_events` n'est jamais réécrit, sauf l'effacement qui vide `detail` (extrait de réponse). Les
  statuts `bounced` / `replied` du message sont conservés après effacement : le fait est gardé, le contenu personnel non.
- **Traçabilité des refus.** Sur l'envoi unitaire (`POST /messages/email|whatsapp`), les refus (`send.blocked_review`,
  `send.blocked_consent`) sont validés en base avant la réponse 403. Les chemins groupés (campagnes, `/batch`) excluent
  silencieusement les destinataires non éligibles, sans ligne d'audit **[à améliorer]**.
- **Conservation.** Aucune purge automatique n'est implémentée **[à valider]** (durées par catégorie de données).
