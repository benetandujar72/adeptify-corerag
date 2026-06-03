#!/usr/bin/env bash
# Porta de verificació local (Linux/macOS/Git Bash).
# Mateixa bateria que la CI: backend pytest + frontend type-check/lint/build.
# Ús: bash scripts/verifica.sh
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"

echo "== backend-pytest =="
cd "$root/backend"
if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate 2>/dev/null || true
fi
python -m pytest -q

echo "== frontend-type-check =="
cd "$root/frontend"
npm run type-check

echo "== frontend-lint =="
npm run lint

echo "== build =="
npm run build

echo ""
echo "OK — porta de verificació verda."
