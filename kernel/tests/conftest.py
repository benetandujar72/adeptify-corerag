"""Fixtures compartides: allowlist signada, kernel d'eines amb eines SINTÈTIQUES.

Cap dada real: les eines retornen contingut sintètic. La clau de capability és de test.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.allowlist import load_signed_allowlist
from app.capabilities import CapabilityIssuer
from app.policy import default_policy
from app.risk import RiskLevel
from app.session import Budget, Deadline, ImmutableContext, Session
from app.tools import Tool, ToolKernel

# Valor de test de baixa entropia (no és cap secret real): >= 16 car. per a l'issuer.
SECRET = "kernel-test-capability-secret-not-real"
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
    tk = ToolKernel(allowlist=allowlist, policy=default_policy(), issuer=issuer)
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
