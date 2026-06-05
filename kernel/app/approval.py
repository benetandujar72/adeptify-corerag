"""F3 · K6.1/K6.2/K6.4 — L'humà al bucle: compuerta propose → approve.

Tota acció de risc ≥2 (write-local o superior) NO s'executa fins que un humà
l'aprova explícitament:

- K6.1  El kernel encunya una `ApprovalRequest` (estat PENDING_APPROVAL). Sense un
        token d'aprovació vàlid lligat a l'acció EXACTA, el kernel no executa res.
- K6.2  Cada proposta porta un resum en LLENGUATGE NATURAL de ≤3 frases: què fa,
        quines dades toca i si és reversible. El resum és DETERMINISTA (es deriva
        de les metadades de l'eina, no del model → no es pot falsejar via injection).
- K6.4  Anti-fatiga: si un aprovador supera 5 aprovacions en 60s, entra en cooldown
        i s'emet una alerta a admin (evita el segell automàtic per fatiga).
- Nivell 4 (IRREVERSIBLE) exigeix DOS aprovadors DISTINTS (llavor de la doble
        validació K6.3, que el SUITE especialitzarà per rol).

INV-1: aquest mòdul NO executa codi arbitrari (només JWT/hash/diccionaris).
INV-2: l'aprovació és una compuerta ADDICIONAL; el RBAC ja s'ha aplicat abans al
        kernel d'eines. Un token d'aprovació no atorga cap escalat de rol.
INV-5: el secret de signatura del token viu al vault; el resum mai conté secrets
        (només metadades de l'eina i els NOMS dels camps, no els valors).
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

import jwt

from .errors import ApprovalError, ApprovalRateLimited
from .risk import RiskLevel

APPROVAL_TYP = "approval"  # marca el JWT com a aprovació (mai capability)


class _ApprovalDisabled:
    """Sentinella d'opt-out EXPLÍCIT de l'aprovació humana (mode F1/F2 o subsistemes
    sense human-gate). És una decisió conscient i auditable; el valor per defecte
    (cap compuerta) és FAIL-CLOSED, no aquest opt-out (F3 · K6.1, hardening red-team)."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "APPROVAL_DISABLED"


APPROVAL_DISABLED = _ApprovalDisabled()


def _normalitza_aprovador(approver_id: object) -> str:
    """Forma canònica de l'identificador d'aprovador.

    Evita que un MATEIX humà compti com a diversos aprovadors «distints» via
    majúscules/minúscules o espais (trencaria la doble validació K6.3) i rebutja
    identificadors buits. Hardening del red-team F3-CORE.
    """
    if not isinstance(approver_id, str):
        raise ApprovalError("approver_id ha de ser una cadena de text")
    canon = approver_id.strip().casefold()
    if not canon:
        raise ApprovalError("approver_id no pot ser buit ni només espais")
    return canon


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def approval_request_id(
    *, session_id: str, tenant_id: str, tool_id: str, args: Mapping[str, Any], risk: int
) -> str:
    """Identificador DETERMINISTA d'una acció proposada.

    Lliga el token a l'acció EXACTA (sessió+tenant+eina+args+risc). Així no es pot
    reaprofitar una aprovació d'una acció per executar-ne una altra (confused deputy).
    """
    core = {
        "session_id": session_id, "tenant_id": tenant_id, "tool_id": tool_id,
        "args": dict(args or {}), "risk": int(risk),
    }
    return hashlib.sha256(_canonical(core).encode("utf-8")).hexdigest()


# ── K6.1 política d'aprovació: quantes aprovacions DISTINTES cal per nivell ──
def aprovacions_requerides(risk: RiskLevel | int) -> int:
    """0 per risc <2; 1 per write-local/external; 2 per IRREVERSIBLE (doble validació)."""
    r = int(risk)
    if r >= int(RiskLevel.IRREVERSIBLE):
        return 2
    if r >= int(RiskLevel.WRITE_LOCAL):
        return 1
    return 0


def requereix_aprovacio(risk: RiskLevel | int) -> bool:
    """Cert si l'acció necessita aprovació humana (risc ≥2)."""
    return aprovacions_requerides(risk) > 0


# ── K6.2 resum en llenguatge natural (≤3 frases, determinista) ──
_REVERSIBILITAT = {
    int(RiskLevel.WRITE_LOCAL): "És una escriptura local, reversible amb còpia de seguretat.",
    int(RiskLevel.WRITE_EXTERNAL): "Escriu en un sistema extern; revertir-ho és difícil.",
    int(RiskLevel.IRREVERSIBLE): "ACCIÓ IRREVERSIBLE: no es pot desfer un cop executada.",
}


def resum_natural(
    *, tool_id: str, risk: RiskLevel | int, args: Mapping[str, Any], descripcio: str = ""
) -> str:
    """Resum de 3 frases: (1) què fa, (2) quines dades toca, (3) reversibilitat.

    No inclou els VALORS dels args (només els noms dels camps) per no filtrar dades
    al resum que veurà l'humà. Es deriva només de metadades → no falsejable (K6.2).
    """
    r = RiskLevel(int(risk))
    # 1 frase: primera frase de la descripció de l'allowlist, o un genèric.
    base = (descripcio or "").split(".")[0].strip()
    que_fa = (base if base else f"Executar l'eina «{tool_id}»") + "."
    # 2 frase: tipus de risc + NOMS dels camps (mai els valors → INV-5).
    claus = ", ".join(sorted(dict(args or {}).keys())) or "cap"
    dades = f"Afecta dades de nivell «{r.etiqueta}» (camps: {claus})."
    # 3 frase: reversibilitat segons el nivell.
    rev = _REVERSIBILITAT.get(int(r), "Reversibilitat desconeguda.")
    return f"{que_fa} {dades} {rev}"


@dataclass(frozen=True)
class ApprovalRequest:
    request_id: str
    session_id: str
    tenant_id: str
    tool_id: str
    risk: int
    resum: str
    aprovacions_requerides: int
    created_at: float


@dataclass
class _PendingState:
    request: ApprovalRequest
    aprovadors: set[str] = field(default_factory=set)  # aprovadors DISTINTS recollits


@dataclass(frozen=True)
class ApprovalOutcome:
    """Resultat de cridar approve(): si encara està pendent o ja s'ha concedit."""
    granted: bool
    recollides: int
    requerides: int
    token: str | None = None


class ApprovalGate:
    """Compuerta humana propose→approve amb anti-fatiga (K6.1/K6.2/K6.4).

    El rellotge és injectable (`clock`) per a tests deterministes, igual que Deadline.
    El secret de signatura ve del vault (INV-5); aquí només se'n guarda la referència.
    """

    def __init__(
        self, *, secret: str, token_ttl_s: int = 300, audit: Any | None = None,
        window_s: float = 60.0, max_per_window: int = 5, cooldown_s: float = 300.0,
        issuer: str = "adeptify-kernel", audience: str = "adeptify-approval",
        algorithm: str = "HS256", clock: Any | None = None,
    ) -> None:
        if not secret or len(secret) < 16:
            raise ApprovalError("El secret d'aprovació ha de tenir >= 16 caràcters")
        self._secret = secret
        self._ttl = int(token_ttl_s)
        self._audit = audit
        self._window_s = float(window_s)
        self._max_per_window = int(max_per_window)
        self._cooldown_s = float(cooldown_s)
        self._iss = issuer
        self._aud = audience
        self._alg = algorithm
        self._clock = clock
        self._pending: dict[str, _PendingState] = {}
        self._historial: dict[str, list[float]] = {}      # aprovador → timestamps (K6.4)
        self._cooldown_fins: dict[str, float] = {}        # aprovador → instant fi cooldown
        self._concedits: dict[str, tuple[int, int]] = {}  # rid → (recollides, requerides) ja concedits
        self._jti_consumits: set[str] = set()             # jtis de tokens JA usats (single-use)

    def _now(self, _now: float | None = None) -> float:
        if _now is not None:
            return _now
        return self._clock() if self._clock else time.time()

    # ── K6.1 PROPOSE: registra la petició i la deixa PENDING_APPROVAL ──
    def propose(
        self, *, session: Any, tool_id: str, risk: RiskLevel | int,
        args: Mapping[str, Any], descripcio: str = "", _now: float | None = None,
    ) -> ApprovalRequest:
        ctx = session.context
        rid = approval_request_id(
            session_id=ctx.session_id, tenant_id=ctx.tenant_id, tool_id=tool_id,
            args=args, risk=int(risk),
        )
        req = ApprovalRequest(
            request_id=rid, session_id=ctx.session_id, tenant_id=ctx.tenant_id,
            tool_id=tool_id, risk=int(risk),
            resum=resum_natural(tool_id=tool_id, risk=risk, args=args, descripcio=descripcio),
            aprovacions_requerides=aprovacions_requerides(risk),
            created_at=self._now(_now),
        )
        # Idempotent per request_id: no es dupliquen aprovadors ja recollits.
        self._pending.setdefault(rid, _PendingState(req))
        self._audit_event(
            actor=f"session:{ctx.session_id}", action="decision:PENDING_APPROVAL",
            tenant_id=ctx.tenant_id,
            payload={"tool_id": tool_id, "risk": int(risk), "request_id": rid,
                     "requerides": req.aprovacions_requerides},
        )
        return req

    # ── K6.4 anti-fatiga: comprova/registra una aprovació d'aquest aprovador ──
    def _comprovar_fatiga(self, approver_id: str, now: float) -> None:
        fins = self._cooldown_fins.get(approver_id, 0.0)
        if now < fins:
            raise ApprovalRateLimited(
                f"Aprovador «{approver_id}» en cooldown anti-fatiga ({fins - now:.0f}s restants)"
            )
        # Frontera inclusiva (<=): una aprovació feta fa EXACTAMENT window_s encara
        # compta dins la finestra (més estricte; hardening del red-team F3-CORE).
        recents = [t for t in self._historial.get(approver_id, []) if now - t <= self._window_s]
        if len(recents) >= self._max_per_window:
            # Supera el llindar (>5/60s): cooldown + ALERTA a admin (K6.4).
            self._cooldown_fins[approver_id] = now + self._cooldown_s
            self._audit_event(
                actor=f"approver:{approver_id}", action="alert:approval_fatigue", tenant_id="",
                payload={"finestra_s": self._window_s, "aprovacions": len(recents),
                         "cooldown_s": self._cooldown_s},
            )
            raise ApprovalRateLimited(
                f"Anti-fatiga: «{approver_id}» supera {self._max_per_window} aprovacions/"
                f"{self._window_s:.0f}s → cooldown {self._cooldown_s:.0f}s i alerta a admin"
            )
        recents.append(now)
        self._historial[approver_id] = recents

    # ── K6.1 APPROVE: acció HUMANA explícita; quan hi ha prou aprovadors, emet token ──
    def approve(
        self, *, request: ApprovalRequest, approver_id: str, _now: float | None = None,
    ) -> ApprovalOutcome:
        now = self._now(_now)
        # H (red-team F4): concessió TERMINAL i idempotent. Si el request ja s'ha
        # concedit, no es reencunya cap token nou ni es consumeix quota anti-fatiga
        # (evita re-mint il·limitat i acumulació de memòria del PENDING).
        if request.request_id in self._concedits:
            recollides, requerides = self._concedits[request.request_id]
            return ApprovalOutcome(True, recollides, requerides, None)
        state = self._pending.get(request.request_id)
        if state is None:
            # Aprovar sense una proposta prèvia no és vàlid.
            raise ApprovalError("No hi ha cap proposta pendent amb aquest request_id")
        approver = _normalitza_aprovador(approver_id)  # canònic: anti-suplantació K6.3
        self._comprovar_fatiga(approver, now)      # K6.4 (pot llançar ApprovalRateLimited)
        state.aprovadors.add(approver)             # DISTINTS: un mateix humà compta 1 cop
        recollides = len(state.aprovadors)
        requerides = state.request.aprovacions_requerides
        self._audit_event(
            actor=f"approver:{approver}", action="decision:APPROVED",
            tenant_id=state.request.tenant_id,
            payload={"tool_id": state.request.tool_id, "request_id": request.request_id,
                     "recollides": recollides, "requerides": requerides},
        )
        if recollides >= requerides:
            token = self._mint(state.request, now)
            self._concedits[request.request_id] = (recollides, requerides)  # H: terminal
            self._pending.pop(request.request_id, None)                     # H: purga PENDING
            return ApprovalOutcome(True, recollides, requerides, token)
        return ApprovalOutcome(False, recollides, requerides, None)

    def _mint(self, request: ApprovalRequest, now: float) -> str:
        payload = {
            "typ": APPROVAL_TYP,
            "request_id": request.request_id,
            "tool_id": request.tool_id,
            "session_id": request.session_id,
            "tenant_id": request.tenant_id,
            "risk_level": request.risk,
            "jti": secrets.token_hex(16),
            "iss": self._iss, "aud": self._aud,
            "iat": int(now), "exp": int(now) + self._ttl,
        }
        return jwt.encode(payload, self._secret, algorithm=self._alg)

    # ── K6.1 verificació del token a l'invoke (lligat a l'acció EXACTA) ──
    def verify_token(
        self, token: str, *, request_id: str, tool_id: str, session_id: str,
    ) -> dict:
        try:
            data = jwt.decode(
                token, self._secret, algorithms=[self._alg], audience=self._aud, issuer=self._iss,
            )
        except jwt.ExpiredSignatureError as exc:
            raise ApprovalError("Token d'aprovació caducat") from exc
        except jwt.InvalidTokenError as exc:
            raise ApprovalError(f"Token d'aprovació invàlid: {exc}") from exc
        if data.get("typ") != APPROVAL_TYP:
            raise ApprovalError("El token no és d'aprovació")
        if data.get("request_id") != request_id:
            raise ApprovalError("El token d'aprovació no lliga amb aquesta acció (request_id)")
        if data.get("tool_id") != tool_id:
            raise ApprovalError("El token d'aprovació és per a una altra eina")
        if data.get("session_id") != session_id:
            raise ApprovalError("El token d'aprovació és per a una altra sessió")
        # G (red-team F4): SINGLE-USE. Un token aprova UNA execució; reutilitzar-lo
        # dins del TTL per re-executar la mateixa acció es rebutja (anti-replay).
        jti = data.get("jti")
        if not jti or jti in self._jti_consumits:
            raise ApprovalError("Token d'aprovació ja consumit o sense jti (single-use)")
        self._jti_consumits.add(jti)
        return data

    def _audit_event(self, *, actor: str, action: str, tenant_id: str, payload: dict) -> None:
        if self._audit is not None:
            self._audit.append(actor=actor, action=action, tenant_id=tenant_id, payload=payload)
