"""K9.1/K9.2 — auditoria hash encadenada + registre de decisions."""

from __future__ import annotations

import dataclasses
import time

from app.audit import EXECUTED, GENESIS, PROPOSED, AuditChain


def test_cadena_encadenada_i_verificable():
    ch = AuditChain()
    e1 = ch.append(actor="a", action="x", tenant_id="tA", payload={"n": 1})
    e2 = ch.append(actor="a", action="y", tenant_id="tA", payload={"n": 2})
    assert e1.prev_hash == GENESIS
    assert e2.prev_hash == e1.hash
    assert ch.verify() is True


def test_manipulacio_trenca_la_cadena():
    ch = AuditChain()
    ch.append(actor="a", action="x", tenant_id="tA", payload={"n": 1})
    ch.append(actor="a", action="y", tenant_id="tA", payload={"n": 2})
    # Manipulem el payload d'una entrada (sense recalcular el hash) → cadena trencada.
    ch._entries[0] = dataclasses.replace(ch._entries[0], payload={"n": 999})
    assert ch.verify() is False


def test_decisio_propost_vs_executat():
    ch = AuditChain()
    ch.record_decision(status=PROPOSED, session_id="s1", tenant_id="tA", tool_id="kv.put_local", risk=2)
    ch.record_decision(status=EXECUTED, session_id="s1", tenant_id="tA", tool_id="kv.put_local", risk=2)
    accions = [e.action for e in ch.entries]
    assert accions == ["decision:PROPOSED", "decision:EXECUTED"]
    assert ch.entries[0].payload["status"] == "PROPOSED"
    assert ch.entries[1].payload["status"] == "EXECUTED"
    assert ch.verify() is True


def test_verificacio_1000_entrades_sota_1s():
    ch = AuditChain()
    for i in range(1000):
        ch.append(actor="bot", action="step", tenant_id="tA", payload={"i": i})
    assert len(ch) == 1000
    t0 = time.perf_counter()
    ok = ch.verify()
    dt = time.perf_counter() - t0
    assert ok is True
    assert dt < 1.0, f"verificació massa lenta: {dt:.3f}s"
