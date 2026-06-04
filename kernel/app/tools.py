"""Kernel d'eines — el punt on s'apliquen RBAC, capabilities i validació d'esquema.

INV-1: cap eina és codi arbitrari; són callables PRE-REGISTRATS. El kernel mai fa
eval/exec del xat, d'un document ni d'un resultat.
INV-2: el RBAC es comprova AQUÍ (kernel), mai al model. El model només PROPOSA un
tool_id i uns args; el kernel decideix i executa.
INV-4: només es poden registrar eines presents a l'allowlist signada (K3.1).
K3.2: validació d'esquema dels args (abans) i del resultat (després) amb pydantic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from .allowlist import SignedAllowlist
from .capabilities import CapabilityIssuer
from .errors import AllowlistError, ArbitraryCodeError, SchemaValidationError
from .policy import PolicyEngine
from .risk import RiskLevel

# fn(args_validats, capability_claims, context_immutable) -> dict (validat pel result_model)
ToolFn = Callable[[BaseModel, Any, Any], dict]


@dataclass
class Tool:
    id: str
    risk: RiskLevel
    args_model: type[BaseModel]
    result_model: type[BaseModel]
    fn: ToolFn
    descripcio: str = ""


class ToolKernel:
    def __init__(self, *, allowlist: SignedAllowlist, policy: PolicyEngine,
                 issuer: CapabilityIssuer, audit: Any | None = None) -> None:
        self._allow = allowlist
        self._policy = policy
        self._issuer = issuer
        self._audit = audit
        self._tools: dict[str, Tool] = {}
        self.executed_count = 0  # nombre d'execucions REALS de fn (per a tests)

    # ── Registre (K3.1 / INV-4) ──
    def register(self, tool: Tool) -> None:
        allowed = self._allow.require(tool.id)  # llança si NO és a l'allowlist signada
        if tool.risk != allowed.risk:
            raise AllowlistError(
                f"Risc de «{tool.id}» ({tool.risk.etiqueta}) != allowlist ({allowed.risk.etiqueta})"
            )
        if not callable(tool.fn):
            raise ArbitraryCodeError("Una eina ha de ser un callable pre-registrat (INV-1)")
        self._tools[tool.id] = tool

    @property
    def registered(self) -> set[str]:
        return set(self._tools)

    # ── Invocació (RBAC + capability + esquema) ──
    def invoke(self, *, session: Any, tool_id: str, args: dict) -> BaseModel:
        ctx = session.context
        tool = self._tools.get(tool_id)
        if tool is None:
            # No registrat / no allowlisted → mai s'executa res (INV-1/INV-4).
            self._decision("DENIED", session, tool_id, RiskLevel.INFO, "no_registrada")
            raise AllowlistError(f"Eina «{tool_id}» no registrada/allowlisted")

        # INV-2: RBAC AQUÍ, al kernel. Es proposa, després es decideix.
        self._decision("PROPOSED", session, tool_id, tool.risk)
        try:
            self._policy.enforce(role=ctx.role, tool_id=tool_id, risk=tool.risk, context=dict(ctx.data))
        except Exception:
            self._decision("DENIED", session, tool_id, tool.risk, "policy")
            raise

        # K2.2: capability de vida curta lligat a (tool, sessió, tenant).
        cap = self._issuer.mint(
            tool_id=tool_id, session_id=ctx.session_id, tenant_id=ctx.tenant_id, risk_level=int(tool.risk)
        )

        # K3.2: valida els args ABANS d'executar.
        try:
            args_obj = tool.args_model.model_validate(args)
        except ValidationError as exc:
            self._decision("DENIED", session, tool_id, tool.risk, "args_schema")
            raise SchemaValidationError(f"Args invàlids per «{tool_id}»: {exc.error_count()} error(s)") from exc

        # L'eina verifica el capability abans d'executar-se (defensa en profunditat).
        claims = self._issuer.verify(cap, expected_tool_id=tool_id, expected_session_id=ctx.session_id)

        # Execució del CALLABLE pre-registrat (mai eval/exec → INV-1).
        self.executed_count += 1
        raw = tool.fn(args_obj, claims, ctx)

        # K3.2: valida el RESULTAT després.
        try:
            result_obj = tool.result_model.model_validate(raw)
        except ValidationError as exc:
            self._decision("DENIED", session, tool_id, tool.risk, "result_schema")
            raise SchemaValidationError(f"Resultat invàlid de «{tool_id}»: {exc.error_count()} error(s)") from exc

        self._decision("EXECUTED", session, tool_id, tool.risk)
        return result_obj

    def _decision(self, status: str, session: Any, tool_id: str, risk: RiskLevel, detail: str = "") -> None:
        if self._audit is not None:
            self._audit.record_decision(
                status=status, session_id=session.id, tenant_id=session.context.tenant_id,
                tool_id=tool_id, risk=int(risk), detail=detail,
            )
