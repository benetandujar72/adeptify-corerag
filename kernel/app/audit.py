"""K9.1/K9.2 — Auditoria append-only amb hash encadenat + registre de decisions.

Cada entrada encadena el hash de l'anterior: hash = SHA-256(prev_hash || core_canònic).
Així qualsevol alteració trenca la cadena (verificable). El registre de decisions
distingeix l'estat: PROPOSED (proposat) vs EXECUTED (executat) vs DENIED vs ESCALATED.

La persistència append-only real (rebuig d'UPDATE/DELETE) s'imposa a la BD amb RLS +
trigger (vegeu db/init/01_rls.sql i db.py). Aquesta classe és la lògica de cadena.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

GENESIS = "0" * 64

# Estats del registre de decisions (K9.2).
PROPOSED = "PROPOSED"
EXECUTED = "EXECUTED"
DENIED = "DENIED"
ESCALATED = "ESCALATED"
PENDING_APPROVAL = "PENDING_APPROVAL"  # F3 · K6.1 — acció ≥2 a l'espera d'aprovació humana
APPROVED = "APPROVED"                  # F3 · K6.1 — aprovació humana enregistrada


def _canonical(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def compute_hash(prev_hash: str, core: dict) -> str:
    return hashlib.sha256((prev_hash + _canonical(core)).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    actor: str
    action: str
    tenant_id: str
    payload: dict
    prev_hash: str
    hash: str

    def core(self) -> dict:
        return {
            "seq": self.seq, "actor": self.actor, "action": self.action,
            "tenant_id": self.tenant_id, "payload": self.payload,
        }


class AuditChain:
    """Cadena d'auditoria append-only amb hash encadenat (en memòria)."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> tuple[AuditEntry, ...]:
        return tuple(self._entries)

    @property
    def head(self) -> str:
        return self._entries[-1].hash if self._entries else GENESIS

    def append(self, *, actor: str, action: str, tenant_id: str = "", payload: dict | None = None) -> AuditEntry:
        seq = len(self._entries) + 1
        prev = self.head
        core = {"seq": seq, "actor": actor, "action": action, "tenant_id": tenant_id, "payload": payload or {}}
        entry = AuditEntry(seq, actor, action, tenant_id, dict(payload or {}), prev, compute_hash(prev, core))
        self._entries.append(entry)
        return entry

    def verify(self) -> bool:
        """Recalcula tota la cadena; retorna False si hi ha cap alteració."""
        prev = GENESIS
        for e in self._entries:
            if e.prev_hash != prev or e.hash != compute_hash(prev, e.core()):
                return False
            prev = e.hash
        return True

    # ── K9.2 registre de decisions (propost vs executat) ──
    def record_decision(self, *, status: str, session_id: str, tenant_id: str,
                        tool_id: str, risk: int, detail: str = "") -> AuditEntry:
        return self.append(
            actor=f"session:{session_id}", action=f"decision:{status}", tenant_id=tenant_id,
            payload={"tool_id": tool_id, "risk": risk, "status": status, "detail": detail},
        )
