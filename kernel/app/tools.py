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
from .approval import (
    APPROVAL_DISABLED, ApprovalGate, approval_request_id, requereix_aprovacio,
)
from .capabilities import CapabilityIssuer
from .errors import (
    AllowlistError, ApprovalError, ApprovalRequired, ArbitraryCodeError, SchemaValidationError,
)
from .policy import PolicyEngine
from .risk import RiskLevel

# fn(args_validats, capability_claims, context_immutable) -> dict (validat pel result_model)
ToolFn = Callable[[BaseModel, Any, Any], dict]


# frozen=True: una eina és IMMUTABLE un cop creada. Impedeix substituir-ne `fn`
# després de l'aprovació humana (defensa en profunditat INV-1/INV-4, hardening red-team).
@dataclass(frozen=True)
class Tool:
    id: str
    risk: RiskLevel
    args_model: type[BaseModel]
    result_model: type[BaseModel]
    fn: ToolFn
    descripcio: str = ""


class ToolKernel:
    def __init__(self, *, allowlist: SignedAllowlist, policy: PolicyEngine,
                 issuer: CapabilityIssuer, audit: Any | None = None,
                 approval_gate: Any = None) -> None:
        self._allow = allowlist
        self._policy = policy
        self._issuer = issuer
        self._audit = audit
        # F3 · K6.1 (secure-by-default, hardening red-team):
        # - ApprovalGate  → tota acció de risc ≥2 exigeix token humà.
        # - APPROVAL_DISABLED → opt-out EXPLÍCIT i auditable (mode F1/F2 sense human-gate).
        # - per defecte (None) → FAIL-CLOSED: cap acció de risc ≥2 s'executa.
        self._gate = approval_gate
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
        if tool.id in self._tools:
            # Cap reescriptura silenciosa d'una eina ja registrada (anti-swap, INV-4).
            raise AllowlistError(f"Eina «{tool.id}» ja registrada (no es permet reescriure)")
        self._tools[tool.id] = tool

    @property
    def registered(self) -> set[str]:
        return set(self._tools)

    def request_id_for(self, *, session: Any, tool_id: str, args: dict) -> str:
        """request_id determinista de l'acció (per casar tokens d'aprovació). F3 · K6.1."""
        ctx = session.context
        tool = self._tools.get(tool_id)
        risk = int(tool.risk) if tool is not None else int(RiskLevel.INFO)
        return approval_request_id(
            session_id=ctx.session_id, tenant_id=ctx.tenant_id, tool_id=tool_id,
            args=args, risk=risk,
        )

    # ── Invocació (RBAC + aprovació humana + capability + esquema) ──
    def invoke(self, *, session: Any, tool_id: str, args: dict,
               approval_token: str | None = None) -> BaseModel:
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

        # F3 · K6.1: humà al bucle. Tota acció de risc ≥2 EXIGEIX aprovació humana
        # ABANS d'executar. El RBAC (INV-2) ja s'ha aplicat: l'aprovació no l'eludeix.
        if requereix_aprovacio(tool.risk):
            if self._gate is APPROVAL_DISABLED:
                pass  # opt-out EXPLÍCIT i auditat (mode F1/F2): cap human-gate.
            elif not isinstance(self._gate, ApprovalGate):
                # FAIL-CLOSED (secure by default): sense compuerta configurada, una
                # acció de risc ≥2 NO s'executa mai. Cal un ApprovalGate o l'opt-out.
                self._decision("DENIED", session, tool_id, tool.risk, "sense_gate_fail_closed")
                raise ApprovalError(
                    "F3 · K6.1: acció de risc ≥2 sense compuerta d'aprovació configurada → "
                    "denegada (fail-closed). Cal un ApprovalGate o APPROVAL_DISABLED explícit."
                )
            else:
                rid = approval_request_id(
                    session_id=ctx.session_id, tenant_id=ctx.tenant_id, tool_id=tool_id,
                    args=args, risk=int(tool.risk),
                )
                if not approval_token:
                    # Sense token → es proposa i s'ESCALA a humà; NO s'executa res.
                    req = self._gate.propose(
                        session=session, tool_id=tool_id, risk=tool.risk, args=args,
                        descripcio=tool.descripcio,
                    )
                    self._decision("PENDING_APPROVAL", session, tool_id, tool.risk, "sense_aprovacio")
                    raise ApprovalRequired(req)
                try:
                    self._gate.verify_token(
                        approval_token, request_id=rid, tool_id=tool_id, session_id=ctx.session_id,
                    )
                except ApprovalError:
                    self._decision("DENIED", session, tool_id, tool.risk, "aprovacio_invalida")
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
