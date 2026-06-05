"""K2.1 — Motor de polítiques allow/deny per rol i context, DENY-BY-DEFAULT.

Motor propi (sense OPA → cap binari/servei extern). L'avaluació és pura i
determinista. La decisió es pren AQUÍ (kernel), mai al model (INV-2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .errors import PolicyDenied
from .risk import RiskLevel


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str


@dataclass(frozen=True)
class AllowRule:
    """Permet a `role` eines fins a `max_risk`. `tools=None` → qualsevol; si no, només
    les llistades. `requires_context` exigeix parells clau/valor al context."""

    role: str
    max_risk: RiskLevel
    tools: frozenset[str] | None = None
    requires_context: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class DenyRule:
    role: str = "*"
    tool_id: str = "*"
    reason: str = "deny explícit"


class PolicyEngine:
    """Avalua (rol, tool_id, risc, context). Deny explícit > allow > deny-by-default."""

    def __init__(self, allow_rules: Iterable[AllowRule], deny_rules: Iterable[DenyRule] = ()) -> None:
        # tuples IMMUTABLES: la decisió RBAC del kernel no es pot alterar in-process
        # afegint regles a _allow/_deny (hardening del red-team TOTAL · INV-2).
        self._allow = tuple(allow_rules)
        self._deny = tuple(deny_rules)

    def evaluate(
        self, *, role: str, tool_id: str, risk: RiskLevel | int,
        context: Mapping[str, Any] | None = None,
    ) -> Decision:
        risk = RiskLevel(int(risk))
        ctx = dict(context or {})

        # 1) Deny explícit (prioritat màxima).
        for d in self._deny:
            if d.role in ("*", role) and d.tool_id in ("*", tool_id):
                return Decision(False, f"DENY explícit: {d.reason}")

        # 2) Regles allow (s'ha de complir alguna).
        for a in self._allow:
            if a.role != role:
                continue
            if risk > a.max_risk:
                continue
            if a.tools is not None and tool_id not in a.tools:
                continue
            if a.requires_context and any(ctx.get(k) != v for k, v in a.requires_context):
                continue
            return Decision(True, f"allow: rol={role}, risc {risk.etiqueta} <= {a.max_risk.etiqueta}")

        # 3) Deny-by-default.
        return Decision(
            False,
            f"DENY-BY-DEFAULT: cap regla permet rol={role} tool={tool_id} risc={risk.etiqueta}",
        )

    def enforce(self, *, role: str, tool_id: str, risk: RiskLevel | int,
                context: Mapping[str, Any] | None = None) -> Decision:
        dec = self.evaluate(role=role, tool_id=tool_id, risk=risk, context=context)
        if not dec.allow:
            raise PolicyDenied(dec.reason)
        return dec


def default_policy() -> PolicyEngine:
    """Política per defecte del kernel.

    viewer → fins READ · operator → fins WRITE_LOCAL · admin/superadmin → fins
    WRITE_EXTERNAL. IRREVERSIBLE (4) NO s'autoritza per defecte a ningú: requereix
    aprovació humana explícita (es modelaria amb una regla allow dedicada + gate humà).
    """
    return PolicyEngine([
        AllowRule("viewer", RiskLevel.READ),
        AllowRule("operator", RiskLevel.WRITE_LOCAL),
        AllowRule("admin", RiskLevel.WRITE_EXTERNAL),
        AllowRule("superadmin", RiskLevel.WRITE_EXTERNAL),
    ])
