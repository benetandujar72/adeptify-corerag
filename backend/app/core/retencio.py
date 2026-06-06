"""Informe de retencio RGPD en mode dry-run.

Aquest modul no esborra ni anonimitza dades. Centralitza la logica compartida
pel CLI i l'endpoint d'administracio per revisar candidats abans d'aprovar una
politica destructiva.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, Conversation, Feedback


DEFAULTS = {
    "converses_dies": 365,
    "feedback_dies": 365,
    "auditoria_dies": 730,
}


def _cutoff(days: int) -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)


def _count_old(db: Session, model, column, cutoff: dt.datetime) -> int:
    return int(db.scalar(select(func.count(model.id)).where(column < cutoff)) or 0)


def build_report(
    db: Session,
    *,
    converses_dies: int = DEFAULTS["converses_dies"],
    feedback_dies: int = DEFAULTS["feedback_dies"],
    auditoria_dies: int = DEFAULTS["auditoria_dies"],
) -> dict[str, Any]:
    """Retorna candidats de retencio sense modificar cap fila."""

    conv_cutoff = _cutoff(converses_dies)
    feedback_cutoff = _cutoff(feedback_dies)
    audit_cutoff = _cutoff(auditoria_dies)
    return {
        "mode": "dry-run",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "policy": {
            "converses_dies": converses_dies,
            "feedback_dies": feedback_dies,
            "auditoria_dies": auditoria_dies,
        },
        "cutoffs": {
            "converses_abans_de": conv_cutoff.isoformat(),
            "feedback_abans_de": feedback_cutoff.isoformat(),
            "auditoria_abans_de": audit_cutoff.isoformat(),
        },
        "candidates": {
            "converses": _count_old(db, Conversation, Conversation.actualitzat_el, conv_cutoff),
            "feedback": _count_old(db, Feedback, Feedback.creat_el, feedback_cutoff),
            "audit_log": _count_old(db, AuditLog, AuditLog.creat_el, audit_cutoff),
        },
        "next_step": (
            "Validar amb DPD/direccio. Qualsevol esborrat real ha de tenir backup, "
            "aprovacio humana i registre d'auditoria."
        ),
    }
