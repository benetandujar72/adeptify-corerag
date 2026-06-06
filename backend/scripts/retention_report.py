"""CLI: informe de retencio RGPD en mode nomes lectura.

No esborra ni anonimitza dades. Calcula quantes files serien candidates segons
els terminis documentats a les EIPD per ajudar el DPD/direccio a validar la
politica abans d'activar cap tasca destructiva.

Us:
    python -m scripts.retention_report
    python -m scripts.retention_report --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import retencio  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402


def build_report(*, converses_dies: int, feedback_dies: int, auditoria_dies: int) -> dict:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as db:
        return retencio.build_report(
            db,
            converses_dies=converses_dies,
            feedback_dies=feedback_dies,
            auditoria_dies=auditoria_dies,
        )


def _text(report: dict[str, Any]) -> str:
    c = report["candidates"]
    p = report["policy"]
    return "\n".join(
        [
            "Adeptify retention report (dry-run)",
            f"Converses > {p['converses_dies']} dies: {c['converses']}",
            f"Feedback > {p['feedback_dies']} dies: {c['feedback']}",
            f"Audit log > {p['auditoria_dies']} dies: {c['audit_log']}",
            "",
            report["next_step"],
        ]
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Informe de retencio RGPD en dry-run.")
    ap.add_argument("--json", action="store_true", help="Sortida JSON.")
    ap.add_argument("--converses-dies", type=int, default=retencio.DEFAULTS["converses_dies"])
    ap.add_argument("--feedback-dies", type=int, default=retencio.DEFAULTS["feedback_dies"])
    ap.add_argument("--auditoria-dies", type=int, default=retencio.DEFAULTS["auditoria_dies"])
    args = ap.parse_args()
    report = build_report(
        converses_dies=args.converses_dies,
        feedback_dies=args.feedback_dies,
        auditoria_dies=args.auditoria_dies,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
