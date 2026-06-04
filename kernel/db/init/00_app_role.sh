#!/bin/bash
# Crea el rol d'aplicació NO-superusuari (subjecte a RLS). La contrasenya ve de
# l'entorn (KERNEL_APP_PASSWORD), mai del repo → gitleaks net.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  DO \$\$
  BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'kernel_app') THEN
      CREATE ROLE kernel_app LOGIN PASSWORD '${KERNEL_APP_PASSWORD}';
    END IF;
  END
  \$\$;
EOSQL
