"""K8.1 — Accés a la BD amb partició per tenant (RLS) i auditoria append-only en BD.

L'app es connecta com a kernel_app (NO superusuari). El tenant actiu es fixa amb
`set_tenant()` (GUC app.tenant_id) i RLS s'encarrega de l'aïllament. L'auditoria a
BD encadena el hash de l'última entrada (coherent amb app/audit.py).
"""

from __future__ import annotations

import json
from typing import Any

import psycopg

from .audit import GENESIS, compute_hash
from .config import get_settings


def connect(dsn: str | None = None, *, autocommit: bool = True) -> psycopg.Connection:
    return psycopg.connect(dsn or get_settings().kernel_db_url, autocommit=autocommit)


def set_tenant(conn: psycopg.Connection, tenant_id: str) -> None:
    """Fixa el tenant actiu de la connexió (RLS el farà servir)."""
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant_id,))


def put_memory(conn: psycopg.Connection, *, tenant_id: str, session_id: str, key: str, value: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO agent_memory (tenant_id, session_id, key, value) VALUES (%s, %s, %s, %s)",
            (tenant_id, session_id, key, json.dumps(value)),
        )


def list_memory(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Llista la memòria VISIBLE (RLS filtra pel tenant actiu)."""
    with conn.cursor() as cur:
        cur.execute("SELECT tenant_id, session_id, key, value FROM agent_memory ORDER BY id")
        return [
            {"tenant_id": r[0], "session_id": r[1], "key": r[2], "value": r[3]}
            for r in cur.fetchall()
        ]


def append_audit(conn: psycopg.Connection, *, tenant_id: str, actor: str, action: str,
                 payload: dict | None = None) -> str:
    """Afegeix una entrada d'auditoria encadenant el hash de l'última (a la BD)."""
    payload = payload or {}
    with conn.cursor() as cur:
        # La cadena s'encadena per CONTINGUT (no pel seq d'identitat de la BD, que
        # amb interleaving entre tenants no seria estable). prev = hash visible més recent.
        cur.execute("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1")
        row = cur.fetchone()
        prev = row[0] if row else GENESIS
        core = {"actor": actor, "action": action, "tenant_id": tenant_id, "payload": payload}
        h = compute_hash(prev, core)
        cur.execute(
            "INSERT INTO audit_log (tenant_id, actor, action, payload, prev_hash, hash) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (tenant_id, actor, action, json.dumps(payload), prev, h),
        )
        return h
