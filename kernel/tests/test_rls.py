"""K8.1/K9.1 (BD) — RLS multi-tenant + auditoria append-only.

Requereix una BD viva (KERNEL_DB_URL). S'executa via docker compose (servei kernel
sobre la xarxa amb kerneldb). Es connecta com a kernel_app (NO superusuari).
"""

from __future__ import annotations

import os

import psycopg
import pytest

from app import db

pytestmark = pytest.mark.skipif(
    not os.environ.get("KERNEL_DB_URL"), reason="sense BD (KERNEL_DB_URL no definit)"
)


def _conn():
    return db.connect(autocommit=True)


def test_tenant_isolation():
    conn = _conn()
    db.set_tenant(conn, "tA")
    db.put_memory(conn, tenant_id="tA", session_id="s1", key="k", value={"v": 1})
    db.set_tenant(conn, "tB")
    db.put_memory(conn, tenant_id="tB", session_id="s2", key="k", value={"v": 2})

    db.set_tenant(conn, "tA")
    rows_a = db.list_memory(conn)
    assert rows_a and all(r["tenant_id"] == "tA" for r in rows_a)  # tA NO veu tB

    db.set_tenant(conn, "tB")
    rows_b = db.list_memory(conn)
    assert rows_b and all(r["tenant_id"] == "tB" for r in rows_b)
    conn.close()


def test_cross_tenant_insert_blocked():
    conn = _conn()
    db.set_tenant(conn, "tA")
    with pytest.raises(psycopg.errors.Error):  # WITH CHECK de RLS ho impedeix
        db.put_memory(conn, tenant_id="tB", session_id="s", key="k", value={})
    conn.close()


def test_audit_append_only_i_cadena():
    conn = _conn()
    db.set_tenant(conn, "tA")
    h1 = db.append_audit(conn, tenant_id="tA", actor="bot", action="step", payload={"i": 1})
    h2 = db.append_audit(conn, tenant_id="tA", actor="bot", action="step", payload={"i": 2})
    assert h1 and h2 and h1 != h2

    # La cadena: prev_hash de la 2a entrada == hash de la 1a (per tenant).
    with conn.cursor() as cur:
        cur.execute("SELECT prev_hash, hash FROM audit_log WHERE hash IN (%s, %s) ORDER BY seq", (h1, h2))
        files = cur.fetchall()
    parells = {h: p for p, h in files}
    assert parells[h2] == h1
    conn.close()


def test_audit_update_delete_rebutjat():
    conn = _conn()
    db.set_tenant(conn, "tA")
    db.append_audit(conn, tenant_id="tA", actor="bot", action="step", payload={"x": 1})
    with conn.cursor() as cur:
        with pytest.raises(psycopg.errors.Error):
            cur.execute("UPDATE audit_log SET action = 'manipulat'")
    conn2 = _conn()
    with conn2.cursor() as cur:
        with pytest.raises(psycopg.errors.Error):
            cur.execute("DELETE FROM audit_log")
    conn.close()
    conn2.close()
