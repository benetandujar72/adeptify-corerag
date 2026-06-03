"""Registre d'auditoria append-only (AI Act + RGPD).

Cada petició a `/api/chat` queda registrada amb: usuari, timestamp, agent
utilitzat, fonts citades i conversation_id. El registre s'escriu de dues
maneres complementàries:

1. A la taula `audit_log` de Postgres (consultable, append-only per disseny).
2. A un fitxer append-only (`AUDIT_LOG_PATH`) com a còpia resistent a la pèrdua
   de la BD, en format JSON-lines.

Mai s'esborren ni es modifiquen registres: és un registre de només-afegir.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AuditLog


def _ara_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _escriu_fitxer(registre: dict[str, Any]) -> None:
    """Afegeix una línia JSON al fitxer d'auditoria (best-effort)."""
    cami = get_settings().audit_log_path
    try:
        Path(cami).parent.mkdir(parents=True, exist_ok=True)
        with open(cami, "a", encoding="utf-8") as fitxer:
            fitxer.write(json.dumps(registre, ensure_ascii=False) + "\n")
    except OSError:
        # No bloquegem la resposta a l'usuari si el fitxer no és escrivible.
        # La còpia a Postgres continua sent la font autoritativa.
        pass


def registra_chat(
    db: Session,
    *,
    usuari: str,
    rol: str,
    agent_utilitzat: str,
    conversation_id: str,
    fonts: list[dict[str, Any]] | None = None,
    message_id: str | None = None,
    intencio: str | None = None,
) -> None:
    """Registra una interacció de xat al log d'auditoria (BD + fitxer).

    `fonts` és la llista de documents citats; només se'n desa la identificació
    (doc_id, filename) per traçabilitat, no el contingut sencer.
    """
    moment = _ara_iso()
    fonts_resum = [
        {"doc_id": f.get("doc_id"), "filename": f.get("filename"), "score": f.get("score")}
        for f in (fonts or [])
    ]
    detalls = {
        "fonts": fonts_resum,
        "intencio": intencio,
        "message_id": message_id,
    }

    db.execute(
        insert(AuditLog).values(
            usuari=usuari,
            rol=rol,
            accio="chat",
            agent=agent_utilitzat,
            conversation_id=conversation_id,
            detalls=detalls,
            creat_el=dt.datetime.now(dt.timezone.utc),
        )
    )
    db.commit()

    _escriu_fitxer(
        {
            "ts": moment,
            "accio": "chat",
            "usuari": usuari,
            "rol": rol,
            "agent": agent_utilitzat,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "intencio": intencio,
            "fonts": fonts_resum,
        }
    )


def registra_accio(
    db: Session,
    *,
    usuari: str,
    rol: str,
    accio: str,
    detalls: dict[str, Any] | None = None,
    base_legal: str | None = None,
) -> None:
    """Registra una acció genèrica auditada (login, ingesta, feedback…).

    `base_legal`: per als accessos a dades de menors (RGPD art. 5.2 «responsabilitat
    proactiva» / AI Act art. 12 «conservació de registres»), la base jurídica
    invocada (p. ex. "6.1.e funció educativa"). Si es passa, queda als `detalls`.
    """
    if base_legal:
        detalls = {**(detalls or {}), "base_legal": base_legal}
    db.execute(
        insert(AuditLog).values(
            usuari=usuari,
            rol=rol,
            accio=accio,
            agent=None,
            conversation_id=None,
            detalls=detalls or {},
            creat_el=dt.datetime.now(dt.timezone.utc),
        )
    )
    db.commit()
    _escriu_fitxer(
        {
            "ts": _ara_iso(),
            "accio": accio,
            "usuari": usuari,
            "rol": rol,
            "detalls": detalls or {},
        }
    )
