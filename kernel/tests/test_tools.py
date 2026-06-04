"""Kernel d'eines: registre (K3.1/INV-4), RBAC al kernel (INV-2), esquema (K3.2)."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.errors import AllowlistError, PolicyDenied, SchemaValidationError
from app.risk import RiskLevel
from app.tools import Tool


class _A(BaseModel):
    x: int
class _R(BaseModel):
    y: int


def test_registrar_eina_fora_allowlist_llanca(tool_kernel):
    evil = Tool("evil.tool", RiskLevel.READ, _A, _R, lambda a, c, x: {"y": 1})
    with pytest.raises(AllowlistError):
        tool_kernel.register(evil)


def test_registrar_risc_incoherent_llanca(tool_kernel):
    # echo.info és INFO a l'allowlist; registrar-lo com READ ha de fallar.
    bad = Tool("echo.info", RiskLevel.READ, _A, _R, lambda a, c, x: {"y": 1})
    with pytest.raises(AllowlistError):
        tool_kernel.register(bad)


def test_invoke_ok_operator(tool_kernel, make_session):
    s = make_session(role="operator")
    res = tool_kernel.invoke(session=s, tool_id="echo.info", args={"msg": "hola"})
    assert res.echo == "hola"
    assert tool_kernel.executed_count == 1


def test_inv2_rbac_al_kernel_viewer_no_escriu(tool_kernel, make_session):
    """INV-2: el RBAC el decideix el KERNEL. Un viewer no executa write-local
    encara que demani l'eina; la fn NO s'executa."""
    s = make_session(role="viewer")
    with pytest.raises(PolicyDenied):
        tool_kernel.invoke(session=s, tool_id="kv.put_local", args={"key": "k", "value": "v"})
    assert tool_kernel.executed_count == 0  # mai s'ha executat la fn


def test_k32_args_invalids_rebutjats(tool_kernel, make_session):
    s = make_session(role="operator")
    with pytest.raises(SchemaValidationError):
        tool_kernel.invoke(session=s, tool_id="echo.info", args={"NO_es_msg": 1})
    assert tool_kernel.executed_count == 0


def test_invoke_no_registrada_llanca(tool_kernel, make_session):
    s = make_session(role="superadmin")
    with pytest.raises(AllowlistError):
        tool_kernel.invoke(session=s, tool_id="inexistent.tool", args={})


def test_irreversible_denegat_per_defecte(tool_kernel, make_session):
    s = make_session(role="superadmin")
    with pytest.raises(PolicyDenied):
        tool_kernel.invoke(session=s, tool_id="fs.delete_all", args={"confirm": True})
