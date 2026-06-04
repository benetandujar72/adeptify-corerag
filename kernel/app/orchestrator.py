"""K1.1 — Orquestrador determinista plan → act → observe.

SENSE bucle implícit: s'executa un PLA finit, pre-produït (un artefacte verificable).
Cada fase deixa un artefacte: el Pla (entrada), les Observacions (act+observe). El
límit de passos (K1.2), el deadline (K1.4) i el RBAC/capabilities (kernel d'eines)
es comproven a cada pas. Si s'exhaureix el budget o el temps, s'ESCALA a humà.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .errors import BudgetExceeded, SessionTimeout, StepLimitExceeded
from .session import Session
from .tools import ToolKernel


@dataclass(frozen=True)
class PlanStep:
    tool_id: str
    args: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Plan:
    """Artefacte de PLA: una seqüència finita de passos (mai s'autogenera en runtime)."""

    steps: tuple[PlanStep, ...] = ()

    @classmethod
    def from_list(cls, items: list[dict]) -> "Plan":
        return cls(tuple(PlanStep(i["tool_id"], dict(i.get("args", {}))) for i in items))


@dataclass(frozen=True)
class Observation:
    step_index: int
    tool_id: str
    ok: bool
    result: Any = None
    error: str | None = None


@dataclass
class RunResult:
    plan_size: int
    observations: list[Observation]
    completed: bool
    escalated: bool = False
    escalation_reason: str | None = None

    @property
    def executed_ok(self) -> int:
        return sum(1 for o in self.observations if o.ok)


class Orchestrator:
    def __init__(self, tool_kernel: ToolKernel, *, clock: Callable[[], float] | None = None) -> None:
        self._tools = tool_kernel
        self._clock = clock  # rellotge monotònic injectable (tests deterministes)

    def run(self, session: Session, plan: Plan) -> RunResult:
        obs: list[Observation] = []
        # PLA BUIT ⇒ no s'executa cap eina.
        for i, step in enumerate(plan.steps, start=1):
            now = self._clock() if self._clock else None
            # K1.4 deadline + K1.2 límit de passos: es comproven ABANS d'actuar.
            try:
                session.deadline.check(_now=now)
                session.budget.charge_step()
            except (SessionTimeout, StepLimitExceeded) as exc:
                return RunResult(len(plan.steps), obs, completed=False,
                                 escalated=True, escalation_reason=str(exc))
            # act + observe
            try:
                result = self._tools.invoke(session=session, tool_id=step.tool_id, args=step.args)
                obs.append(Observation(i, step.tool_id, ok=True, result=result))
            except BudgetExceeded as exc:
                return RunResult(len(plan.steps), obs, completed=False,
                                 escalated=True, escalation_reason=str(exc))
            except Exception as exc:  # política/esquema/allowlist → observació d'error i atura
                obs.append(Observation(i, step.tool_id, ok=False, error=f"{type(exc).__name__}: {exc}"))
                return RunResult(len(plan.steps), obs, completed=False)
        return RunResult(len(plan.steps), obs, completed=True)
