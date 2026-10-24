# AGENTS.md — Plantiers – OutreachOS

## Mission produit
Plantiers est un OS de prospection mondiale pour vendre des solutions digitales.
Objectif : découvrir des prospects réels, les enrichir, les qualifier, les contacter par email/WhatsApp/appels IA, suivre les réponses et générer des rendez-vous.

## Règles non négociables
- Aucun mock, fake, placeholder, donnée statique ou donnée inventée dans les parcours métier.
- Supabase est la source de vérité.
- Le service_role Supabase reste exclusivement côté backend.
- RLS obligatoire sur toute table exposée.
- Aucun secret dans le code, les tests, les logs, le frontend ou les commits.
- Ne jamais accéder aux secrets Render, Supabase, SMTP, IMAP, Twilio, SendGrid ou Groq.
- Ne jamais pousser sur main.
- Toujours livrer une PR courte, testable et déployable.
- Aucune dépendance payante nouvelle sans validation explicite.
- Privilégier les sources gratuites : OpenStreetMap/Overpass, geo.api.gouv.fr, recherche-entreprises.api.gouv.fr, pages publiques des sites prospects.
- Optimiser les coûts : cache, batch, pagination, jobs asynchrones, requêtes SQL indexées, pas d’appel IA inutile.
- Ne jamais envoyer d’email ou WhatsApp sans passer par les vérifications de conformité et les limites existantes.

## Stack
- Frontend : React/TypeScript, déployé sur Netlify.
- API : Node/TypeScript, déployée sur Render.
- Base : Supabase Postgres + session pooler.
- IA : Groq, modèle llama-3.1-8b-instant.
- Email : SMTP Hostinger + IMAP Hostinger.
- WhatsApp : Twilio, non configuré pour l’instant.
- Sources : Overpass, geo.api.gouv.fr, recherche-entreprises.api.gouv.fr.

## Intégrations actuelles
- Database : CONNECTED.
- Public URL : CONFIGURED.
- Overpass : KEYLESS, multiple endpoints.
- Town search : KEYLESS, appelé depuis le navigateur.
- French company registry : KEYLESS, FEATURE_EXTERNAL_SOURCES=on.
- SMTP : CONFIGURED, TLS obligatoire.
- IMAP : CONFIGURED, lecture seule, port 993.
- Sender identity : founder@plantiers.com.
- Sending mode : LIVE, mais respecter sandbox, allowlist, kill switch et limites.
- AI composer : CONFIGURED via Groq.

## Règles d’envoi
- Respecter OUTREACH_SANDBOX, OUTREACH_LIVE_ALLOWLIST, OUTREACH_LIVE_PHONES et SEND_KILL_SWITCH.
- Aucun contournement du sandbox.
- Aucun envoi WhatsApp sans opt-in explicite.
- Chaque email doit contenir l’identité de l’expéditeur, l’origine de la donnée et un lien de désinscription réel.
- Toute désinscription doit être immédiate, persistante et globale.

## Qualité
- TypeScript strict.
- Migrations Supabase idempotentes.
- Index sur les colonnes de recherche, jointure, statut et timestamps.
- Validation Zod sur toute entrée API.
- Logs structurés : request_id, workspace_id, job_id, source, duration_ms, status, error_code.
- Tests backend, tests frontend, Playwright, lint et build obligatoirement verts.
- Ne jamais laisser de TODO, console.log inutile ou code mort.

## Workflow Git
1. Créer une branche descriptive.
2. Implémenter une seule mission par PR.
3. Ajouter ou mettre à jour les tests.
4. Exécuter lint, tests et build.
5. Ouvrir une PR avec : objectif, changements, migrations, variables, risques, plan de test production.
6. Ne jamais merger sans validation humaine.

## Commandes
Utilise les commandes existantes du repo. Si le package manager ou les scripts diffèrent, détecte-les d’abord dans package.json avant d’exécuter quoi que ce soit.