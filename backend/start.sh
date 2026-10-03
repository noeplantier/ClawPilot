#!/bin/sh
# Container entrypoint: apply the database migrations, then serve on the port the platform gives us.
# Render sets PORT (10000); docker-compose and local runs fall back to 8000.
# RUN_MIGRATIONS=0 skips the migration step (e.g. when a platform release step already runs `alembic upgrade head`).
set -e
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  alembic upgrade head
fi
exec uvicorn server:app --host 0.0.0.0 --port "${PORT:-8000}"
