"""CLI: imprimeix l'estat de producció. Codi de sortida ≠0 si hi ha avisos/crítics.

Ús:
    python -m scripts.produccio_check          # text llegible
    python -m scripts.produccio_check --json   # JSON crus per a Cron / pipelines

Cron exemple (UTC):
    0 6 * * 1  /app/.venv/bin/python -m scripts.produccio_check >> /var/log/adeptify/produccio.log
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.security.produccio_check import executa_check, formata_text  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Estat de producció d'Adeptify.")
    ap.add_argument("--json", action="store_true", help="Sortida en JSON.")
    args = ap.parse_args()

    report = executa_check()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(formata_text(report))

    sev = report["severitat_global"]
    return 0 if sev in ("ok", "info") else 1


if __name__ == "__main__":
    raise SystemExit(main())
