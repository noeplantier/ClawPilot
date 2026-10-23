# Utiliser Supabase comme base de données

Supabase est ici un **PostgreSQL géré** : l'API (FastAPI) s'y connecte par `DATABASE_URL`, exactement comme à n'importe quel
PostgreSQL, et Alembic applique les migrations au démarrage (`start.sh`). Le frontend ne parle pas à Supabase : il appelle l'API
(authentification maison, JWT), il n'y a donc **pas de clé Supabase dans le navigateur** et `service_role` n'est jamais utilisée.

## Brancher la base (Render → Supabase)
1. Supabase → *Project Settings → Database → Connection string → **Session pooler*** (port **5432**, hôte `aws-0-…pooler.supabase.com`,
   utilisateur `postgres.<ref>`). Ne pas prendre « Direct connection » : elle est en IPv6 seulement sur l'offre gratuite et Render n'a
   pas de route IPv6 (même cause que l'erreur `Network is unreachable` vue sur Overpass). Ne pas prendre non plus le « Transaction pooler »
   (port 6543) : il ne gère pas les requêtes préparées d'asyncpg.
2. Render → service `clawpilot-api` → *Environment* → `DATABASE_URL` = cette adresse, **saisie dans Render, jamais dans un chat, un
   commit ou un ticket**. Un mot de passe contenant `@`, `%` ou `/` doit être encodé en URL (`%40`…) : c'est géré (Alembic échappe `%`).
3. Redéployer : `alembic upgrade head` crée le schéma, y compris l'activation de la sécurité par ligne (ci-dessous).
4. Vérifier : page `/app/system` (base « Supabase (session pooler) », migrations à jour).

## Sécurité par ligne (RLS)
Supabase expose le schéma `public` par son API de données avec la clé publique `anon`. La migration `a8c4d5e6f7b9` active la RLS **sans
aucune politique** sur toutes les tables (refus par défaut pour `anon` et `authenticated`) et retire leurs droits quand ces rôles existent ;
l'API se connecte en propriétaire des tables, qui contourne la RLS : rien ne change pour elle. Un test échoue si une table du schéma
`public` est créée sans RLS : toute nouvelle migration qui ajoute une table doit l'activer.

## Les données de la base Render actuelle
La base gratuite de Render **expire le 2 novembre 2026**. Ce sont des données de test : repartir à vide sur Supabase est le plus simple.
Pour les garder : `pg_dump --no-owner --no-privileges "<url Render>" | psql "<url Supabase session pooler>"` depuis un poste qui a les deux
adresses (à faire avant l'expiration ; les deux adresses restent chez vous).

## Retour arrière
Remettre l'ancienne `DATABASE_URL` dans Render et redéployer (la base Render doit exister encore). Les migrations sont réversibles sauf
la RLS, qui reste active volontairement.
