"""K1.2/K1.3/K1.4 — Sessió: context immutable, pressupostos i timeout absolut.

- K1.3 ImmutableContext: un cop creat, mutar-lo llança ImmutableViolation. Té un
  digest SHA-256 verificable del seu contingut canònic.
- K1.2 Budget: límit de passos (def. 10, màx. 25) i token_budget. Superar passos →
  StepLimitExceeded; superar tokens → BudgetExceeded (escala a humà).
- K1.4 Deadline: timeout absolut basat en rellotge monotònic, fixat en crear la
  sessió i NO extensible des de dins del loop.
"""

from __future__ import annotations

import hashlib
import json
import time
from types import MappingProxyType
from typing import Any, Mapping

from .errors import BudgetExceeded, ImmutableViolation, SessionTimeout, StepLimitExceeded


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


class ImmutableContext:
    """Context de sessió immutable amb digest SHA-256 verificable (K1.3)."""

    __slots__ = ("_d", "_data", "_digest", "_frozen")

    def __init__(
        self, *, session_id: str, tenant_id: str, role: str,
        created_at: float | None = None, data: Mapping[str, Any] | None = None,
    ) -> None:
        d = {
            "session_id": session_id,
            "tenant_id": tenant_id,
            "role": role,
            "created_at": created_at if created_at is not None else time.time(),
            "data": dict(data or {}),
        }
        object.__setattr__(self, "_d", d)
        object.__setattr__(self, "_data", MappingProxyType(d["data"]))  # vista read-only
        object.__setattr__(self, "_digest", hashlib.sha256(_canonical(d).encode("utf-8")).hexdigest())
        object.__setattr__(self, "_frozen", True)

    # ── Accés de només lectura ──
    @property
    def session_id(self) -> str: return self._d["session_id"]
    @property
    def tenant_id(self) -> str: return self._d["tenant_id"]
    @property
    def role(self) -> str: return self._d["role"]
    @property
    def created_at(self) -> float: return self._d["created_at"]
    @property
    def data(self) -> Mapping[str, Any]: return self._data
    @property
    def digest(self) -> str: return self._digest

    def verify_integrity(self) -> bool:
        """Recalcula el digest i comprova que el contingut no s'ha alterat."""
        return hashlib.sha256(_canonical(self._d).encode("utf-8")).hexdigest() == self._digest

    # ── Immutabilitat ──
    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_frozen", False):
            raise ImmutableViolation(f"El context de sessió és immutable (intent d'escriure «{name}»)")
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        raise ImmutableViolation("El context de sessió és immutable (intent d'esborrar)")

    def __repr__(self) -> str:
        return f"<ImmutableContext session={self.session_id} tenant={self.tenant_id} role={self.role} digest={self._digest[:12]}…>"


class Budget:
    """Pressupost de passos i tokens (K1.2). Els LÍMITS són fixos; els comptadors muten."""

    def __init__(self, *, max_steps: int = 10, max_steps_hard: int = 25, token_budget: int = 20000) -> None:
        if max_steps < 1:
            raise ValueError("max_steps ha de ser >= 1")
        # Sostre absolut: cap sessió pot demanar-ne més (K1.2).
        self.max_steps = min(int(max_steps), int(max_steps_hard))
        self.token_budget = int(token_budget)
        self.steps_used = 0
        self.tokens_used = 0

    def charge_step(self) -> int:
        """Compta un pas ABANS d'executar-lo. Llança si superaria el límit."""
        self.steps_used += 1
        if self.steps_used > self.max_steps:
            raise StepLimitExceeded(
                f"STEP_LIMIT: pas {self.steps_used} supera el límit de {self.max_steps}"
            )
        return self.steps_used

    def charge_tokens(self, n: int) -> int:
        self.tokens_used += max(0, int(n))
        if self.tokens_used > self.token_budget:
            raise BudgetExceeded(
                f"BUDGET_EXCEEDED: {self.tokens_used} > {self.token_budget} tokens — escala a humà"
            )
        return self.tokens_used


class Deadline:
    """Timeout absolut de sessió (K1.4): monotònic, fixat en crear, no extensible."""

    __slots__ = ("_deadline", "_timeout_s")

    def __init__(self, timeout_s: float, *, _now: float | None = None) -> None:
        now = _now if _now is not None else time.monotonic()
        object.__setattr__(self, "_timeout_s", float(timeout_s))
        object.__setattr__(self, "_deadline", now + float(timeout_s))

    @property
    def timeout_s(self) -> float: return self._timeout_s

    def remaining(self, *, _now: float | None = None) -> float:
        now = _now if _now is not None else time.monotonic()
        return self._deadline - now

    def expired(self, *, _now: float | None = None) -> bool:
        return self.remaining(_now=_now) <= 0

    def check(self, *, _now: float | None = None) -> None:
        """Llança SessionTimeout si s'ha superat el deadline (el crida el loop)."""
        if self.expired(_now=_now):
            raise SessionTimeout(f"SESSION_TIMEOUT: superats {self._timeout_s:.0f}s")

    # No hi ha cap mètode per estendre/cancel·lar el deadline des de dins del loop.
    def __setattr__(self, *_a: Any) -> None:
        raise ImmutableViolation("El deadline de sessió no es pot modificar des de dins")


class Session:
    """Agrupa context immutable + budget + deadline."""

    def __init__(self, context: ImmutableContext, budget: Budget, deadline: Deadline) -> None:
        self.context = context
        self.budget = budget
        self.deadline = deadline

    @property
    def id(self) -> str:
        return self.context.session_id
