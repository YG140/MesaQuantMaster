#!/usr/bin/env bash
# Free Render does not support a pre-deploy command.
# Start only after Neon Postgres is configured and migrations have succeeded.
set -euo pipefail

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL ausente: configure a string PostgreSQL Neon na Render (Environment)." >&2
  exit 1
fi
if [[ -z "${SECRET_KEY:-}" ]]; then
  echo "SECRET_KEY ausente: configure segredo forte no Render." >&2
  exit 1
fi

# Never print environment variables or URL (database credentials).
# Free instances restart on idle; Alembic upgrade head is idempotent.
python -m alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}" --workers 1
