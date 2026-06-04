"""Fixtures compartides: allowlist signada, kernel d'eines amb eines SINTÈTIQUES.

Cap dada real: les eines retornen contingut sintètic. La clau de capability és de test.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.allowlist import load_signed_allowlist
from app.approval import APPROVAL_DISABLED, ApprovalGate
from app.audit import AuditChain
from app.capabilities import CapabilityIssuer
from app.policy import AllowRule, PolicyEngine, default_policy
from app.risk import RiskLevel
from app.session import Budget, Deadline, ImmutableContext, Session
from app.tools import Tool, ToolKernel

# Valor de test de baixa entropia (no és cap secret real): >= 16 car. per a l'issuer.
SECRET = "kernel-test-capability-secret-not-real"
# Secret d'aprovació de test (baixa entropia, no real): separat del de capability.
APPROVAL_SECRET = "kernel-test-approval-secret-not-real"
AL = "/app/allowlist"


# ── Esquemes (K3.2) de les eines sintètiques ──
class EchoArgs(BaseModel):
    msg: str
class EchoResult(BaseModel):
    echo: str
class ReadArgs(BaseModel):
    doc_id: str
class ReadResult(BaseModel):
    content: str
class KvArgs(BaseModel):
    key: str
    value: str
class KvResult(BaseModel):
    ok: bool
class NotifyArgs(BaseModel):
    to: str
    msg: str
class NotifyResult(BaseModel):
    sent: bool
class DeleteArgs(BaseModel):
    confirm: bool
class DeleteResult(BaseModel):
    deleted: int


def synthetic_tools() -> list[Tool]:
    return [
        Tool("echo.info", RiskLevel.INFO, EchoArgs, EchoResult,
             lambda a, c, x: {"echo": a.msg}),
        Tool("fs.read_synthetic", RiskLevel.READ, ReadArgs, ReadResult,
             lambda a, c, x: {"content": f"contingut sintètic de {a.doc_id}"}),
        Tool("kv.put_local", RiskLevel.WRITE_LOCAL, KvArgs, KvResult,
             lambda a, c, x: {"ok": True}),
        Tool("notify.external", RiskLevel.WRITE_EXTERNAL, NotifyArgs, NotifyResult,
             lambda a, c, x: {"sent": True}),
        Tool("fs.delete_all", RiskLevel.IRREVERSIBLE, DeleteArgs, DeleteResult,
             lambda a, c, x: {"deleted": 0}),
    ]


@pytest.fixture
def allowlist():
    return load_signed_allowlist(
        data_path=f"{AL}/tools.yaml", sig_path=f"{AL}/tools.yaml.sig",
        pubkey_path=f"{AL}/pubkey.asc",
    )


@pytest.fixture
def issuer():
    return CapabilityIssuer(SECRET)


@pytest.fixture
def tool_kernel(allowlist, issuer):
    # Mode F1/F2 EXPLÍCIT: sense human-gate (opt-out auditable). El defecte seria
    # fail-closed per a risc ≥2 (hardening red-team F3-CORE).
    tk = ToolKernel(allowlist=allowlist, policy=default_policy(), issuer=issuer,
                    approval_gate=APPROVAL_DISABLED)
    for t in synthetic_tools():
        tk.register(t)
    return tk


@pytest.fixture
def make_session():
    def _mk(*, role="operator", tenant="tA", session_id="s1", timeout_s=120.0,
            max_steps=10, data=None) -> Session:
        ctx = ImmutableContext(session_id=session_id, tenant_id=tenant, role=role, data=data or {})
        return Session(ctx, Budget(max_steps=max_steps), Deadline(timeout_s))
    return _mk


# ── Fixtures F3 (compuerta d'aprovació humana) ──
# Nota: el `exp` del JWT el valida la llibreria contra el rellotge REAL, no contra
# cap rellotge injectat. Per això la porta usa el rellotge real i els tests dirigeixen
# el temps de l'anti-fatiga (K6.4) passant `_now=` a approve() (no afecta el JWT).
@pytest.fixture
def audit():
    return AuditChain()


@pytest.fixture
def approval_gate(audit):
    return ApprovalGate(secret=APPROVAL_SECRET, audit=audit)


def _policy_amb_irreversible() -> PolicyEngine:
    """Política de test que SÍ permet IRREVERSIBLE al rol 'superadmin' (per provar
    que, tot i així, una sola aprovació no executa accions de nivell 4)."""
    return PolicyEngine([
        AllowRule("viewer", RiskLevel.READ),
        AllowRule("operator", RiskLevel.WRITE_LOCAL),
        AllowRule("admin", RiskLevel.WRITE_EXTERNAL),
        AllowRule("superadmin", RiskLevel.IRREVERSIBLE),
    ])


@pytest.fixture
def gated_tool_kernel(allowlist, issuer, approval_gate, audit):
    """Kernel d'eines AMB compuerta d'aprovació (F3) i política que permet nivell 4."""
    tk = ToolKernel(
        allowlist=allowlist, policy=_policy_amb_irreversible(), issuer=issuer,
        audit=audit, approval_gate=approval_gate,
    )
    for t in synthetic_tools():
        tk.register(t)
    return tk
