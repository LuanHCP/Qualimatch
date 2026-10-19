#!/bin/sh
set -e

echo "[entrypoint] Aguardando PostgreSQL em ${PGHOST:-db}:${PGPORT:-5432} ..."
i=0
until PGPASSWORD="$PGPASSWORD" psql -h "${PGHOST:-db}" -p "${PGPORT:-5432}" -U "${PGUSER:-nc_app}" -d "${PGDATABASE:-nc_sistema}" -c 'select 1' >/dev/null 2>&1; do
  i=$((i+1))
  if [ "$i" -ge 60 ]; then
    echo "[entrypoint] PostgreSQL não respondeu a tempo." >&2
    exit 1
  fi
  sleep 1
done
echo "[entrypoint] PostgreSQL disponível."

echo "[entrypoint] Aplicando migrations ..."
python3 migrate.py

if [ -n "$BOOTSTRAP_ADMIN_EMAIL" ] && [ -n "$BOOTSTRAP_ADMIN_PASSWORD" ]; then
  echo "[entrypoint] Garantindo administrador inicial ($BOOTSTRAP_ADMIN_EMAIL) ..."
  python3 bootstrap_admin.py || true
fi

exec "$@"
