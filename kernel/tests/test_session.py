"""K1.2/K1.3/K1.4 — sessió immutable, budgets i deadline."""

from __future__ import annotations

import pytest

from app.errors import BudgetExceeded, ImmutableViolation, SessionTimeout, StepLimitExceeded
from app.session import Budget, Deadline, ImmutableContext


def _ctx():
    return ImmutableContext(session_id="s1", tenant_id="tA", role="operator",
                            created_at=1000.0, data={"k": "v"})


# ── K1.3 context immutable + digest ──
def test_digest_estable_i_verificable():
    c = _ctx()
    assert len(c.digest) == 64
    assert c.verify_integrity() is True
    # mateix contingut → mateix digest (verificable).
    assert ImmutableContext(session_id="s1", tenant_id="tA", role="operator",
                            created_at=1000.0, data={"k": "v"}).digest == c.digest


def test_mutacio_atribut_llanca():
    c = _ctx()
    with pytest.raises(ImmutableViolation):
        c.role = "admin"  # type: ignore[misc]
    with pytest.raises(ImmutableViolation):
        del c.role  # type: ignore[misc]


def test_data_es_read_only():
    c = _ctx()
    with pytest.raises(TypeError):
        c.data["k"] = "x"  # MappingProxyType → no es pot escriure


# ── K1.2 budgets ──
def test_step_limit_atura_al_pas_4_amb_limit_3():
    b = Budget(max_steps=3)
    assert [b.charge_step() for _ in range(3)] == [1, 2, 3]
    with pytest.raises(StepLimitExceeded):
        b.charge_step()  # pas 4 → s'atura


def test_max_steps_acotat_al_sostre():
    b = Budget(max_steps=100, max_steps_hard=25)
    assert b.max_steps == 25  # cap sessió pot superar el sostre absolut


def test_token_budget_escala():
    b = Budget(token_budget=1000)
    b.charge_tokens(900)
    with pytest.raises(BudgetExceeded):
        b.charge_tokens(200)  # BUDGET_EXCEEDED → escala a humà


# ── K1.4 deadline absolut ──
def test_deadline_expira_i_no_extensible():
    dl = Deadline(timeout_s=10, _now=1000.0)
    assert dl.remaining(_now=1005.0) == pytest.approx(5.0)
    assert dl.expired(_now=1005.0) is False
    dl.check(_now=1005.0)  # no llança
    assert dl.expired(_now=1011.0) is True
    with pytest.raises(SessionTimeout):
        dl.check(_now=1011.0)
    # no extensible des de dins
    with pytest.raises(ImmutableViolation):
        dl._deadline = 99999999.0  # type: ignore[attr-defined]
