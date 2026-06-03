#!/usr/bin/env bash
# ---------------------------------------------------------------
#  adeptify-corerag — one-time setup of the zero-leak hooks.
#  Installs pre-commit + gitleaks hooks and runs a first full scan.
#  Usage:  bash scripts/install-hooks.sh
# ---------------------------------------------------------------
set -euo pipefail

echo "==> Installing pre-commit"
if ! command -v pre-commit >/dev/null 2>&1; then
  python3 -m pip install --user pre-commit
fi

echo "==> Installing the git pre-commit hook"
pre-commit install

echo "==> Pinning the latest hook revisions"
pre-commit autoupdate || true

echo "==> First full pass over the working tree"
pre-commit run --all-files || true

echo
echo "==> IMPORTANT: before making the repository public, scan the FULL git history:"
if command -v gitleaks >/dev/null 2>&1; then
  gitleaks detect --source . --redact -v --config .gitleaks.toml || {
    echo "!! gitleaks found potential secrets in the history. Clean them"
    echo "   (git filter-repo / BFG) and ROTATE the affected secrets before publishing."
    exit 1
  }
else
  echo "   gitleaks binary not found. Install it (https://github.com/gitleaks/gitleaks)"
  echo "   and run:  gitleaks detect --source . --redact -v --config .gitleaks.toml"
fi

echo
echo "Done. Every commit is now scanned locally; CI scans every push/PR."
