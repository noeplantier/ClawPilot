"""row level security on every table of the public schema (deny by default for the Data API)

Revision ID: a8c4d5e6f7b9
Revises: f6a2b3c4d5e7
Create Date: 2026-10-23 09:40:00.000000

Supabase exposes the `public` schema through its Data API (PostgREST) with the public anon key. Without RLS every table
would be readable and writable by anyone holding that key. The application never uses the Data API: it connects to Postgres
as the table owner (which bypasses RLS), so enabling RLS with NO policy closes the Data API completely and changes nothing for
the backend. On plain PostgreSQL (CI, local) the roles `anon` / `authenticated` do not exist and only RLS is enabled.
Idempotent: safe to run again, and every later migration that adds a table must enable RLS too (a test enforces it).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a8c4d5e6f7b9"
down_revision: Union[str, Sequence[str], None] = "f6a2b3c4d5e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = """
DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t.tablename);
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM authenticated';
  END IF;
END $$;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    # Re-opening the Data API is never wanted: the downgrade keeps RLS on. Revert the map tables only through f6a2b3c4d5e7.
    pass
