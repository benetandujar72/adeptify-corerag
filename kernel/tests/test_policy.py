"""K2.1 — Motor de polítiques deny-by-default (cobertura alta, table-driven)."""

from __future__ import annotations

import pytest

from app.errors import PolicyDenied
from app.policy import AllowRule, DenyRule, PolicyEngine, default_policy
from app.risk import RiskLevel

POL = default_policy()


def test_redteam_politica_immutable_no_mutable_in_process():
    """Red-team TOTAL (INV-2 hardening): les regles es desen en tuples IMMUTABLES;
    cap codi in-process pot afegir una regla per escalar el RBAC del kernel."""
    pe = PolicyEngine([AllowRule("viewer", RiskLevel.READ)])
    assert isinstance(pe._allow, tuple) and isinstance(pe._deny, tuple)
    with pytest.raises(AttributeError):
        pe._allow.append(AllowRule("viewer", RiskLevel.WRITE_LOCAL))  # tuple: sense append

# Matriu rol × risc → permès? (cobertura de la taula de decisió).
MATRIU = [
    ("viewer", RiskLevel.INFO, True),
    ("viewer", RiskLevel.READ, True),
    ("viewer", RiskLevel.WRITE_LOCAL, False),     # ← viewer NO escriu encara que ho demani
    ("viewer", RiskLevel.WRITE_EXTERNAL, False),
    ("viewer", RiskLevel.IRREVERSIBLE, False),
    ("operator", RiskLevel.READ, True),
    ("operator", RiskLevel.WRITE_LOCAL, True),
    ("operator", RiskLevel.WRITE_EXTERNAL, False),
    ("operator", RiskLevel.IRREVERSIBLE, False),
    ("admin", RiskLevel.WRITE_EXTERNAL, True),
    ("admin", RiskLevel.IRREVERSIBLE, False),     # irreversible mai per defecte
    ("superadmin", RiskLevel.IRREVERSIBLE, False),
    ("desconegut", RiskLevel.INFO, False),        # rol desconegut → deny-by-default
]


@pytest.mark.parametrize("role,risk,permes", MATRIU)
def test_matriu_rol_risc(role, risk, permes):
    dec = POL.evaluate(role=role, tool_id="t.demo", risk=risk)
    assert dec.allow is permes, dec.reason


def test_viewer_write_enforce_llanca():
    with pytest.raises(PolicyDenied):
        POL.enforce(role="viewer", tool_id="fs.write", risk=RiskLevel.WRITE_LOCAL)


def test_deny_explicit_te_prioritat():
    pol = PolicyEngine(
        allow_rules=[AllowRule("admin", RiskLevel.WRITE_EXTERNAL)],
        deny_rules=[DenyRule(role="admin", tool_id="fs.delete", reason="prohibit")],
    )
    assert pol.evaluate(role="admin", tool_id="fs.read", risk=RiskLevel.READ).allow is True
    assert pol.evaluate(role="admin", tool_id="fs.delete", risk=RiskLevel.READ).allow is False


def test_tools_allowlist_per_regla():
    pol = PolicyEngine([AllowRule("operator", RiskLevel.WRITE_LOCAL, tools=frozenset({"fs.write"}))])
    assert pol.evaluate(role="operator", tool_id="fs.write", risk=RiskLevel.WRITE_LOCAL).allow is True
    assert pol.evaluate(role="operator", tool_id="altra", risk=RiskLevel.READ).allow is False


def test_requires_context():
    pol = PolicyEngine([AllowRule("operator", RiskLevel.READ, requires_context=(("network", "lan"),))])
    assert pol.evaluate(role="operator", tool_id="t", risk=RiskLevel.READ, context={"network": "lan"}).allow is True
    assert pol.evaluate(role="operator", tool_id="t", risk=RiskLevel.READ, context={"network": "wan"}).allow is False
    assert pol.evaluate(role="operator", tool_id="t", risk=RiskLevel.READ).allow is False
