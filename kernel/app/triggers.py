"""K15·F5c — Triggers declaratius SIGNATS, en mode PROPOSE-ONLY i avaluació PURA.

Estén el scheduler (K11) als triggers per CONDICIÓ (no només per temps), però mantenint
exactament les mateixes garanties (gates G-A/G-G, INV-1/INV-3):

- **Cap runner de fons ni async** (G-A). `RUNNER_ACTIU = False`. L'avaluació és una funció
  PURA que un disparador EXTERN (el mateix patró d'OPS que el scheduler) crida amb una
  instantània d'observacions; aquí no hi ha cap bucle autònom ni cap port/webhook (INV-3).
- **Condició declarativa, SENSE `eval`** (INV-1). Una condició és `camp OP valor` amb un
  operador d'un conjunt TANCAT i un valor numèric. Mai s'avalua codi del text.
- **Snapshot només numèric/booleà** (frontera PII, fail-closed). Si el camp observat no és
  un nombre/booleà, es rebutja: el CORE no compara dades lliures (que podrien dur PII).
- **Propose-only** (K6/INV-1). En disparar-se, NO s'executa res: s'instancia el playbook
  signat → `Plan` i s'ENCUA una proposta d'aprovació per pas, com el scheduler. Un humà
  decideix; el trigger només DIU "potser toca", mai actua.
- **Tot signat i validat encreuat** (INV-4/G-D): cada trigger referencia un `playbook` del
  catàleg signat; la càrrega exigeix la mateixa firma GPG amb pinning que la resta.
"""

from __future__ import annotations

import math
import operator
import pathlib
from dataclasses import dataclass, field

import strictyaml

from .allowlist import SignedAllowlist, fingerprint_de_confianca, verify_gpg_signature
from .approval import ApprovalGate, ApprovalRequest
from .errors import TriggerError
from .orchestrator import Plan
from .playbooks import SignedPlaybookCatalog, instantiate

# Cap runner de fons (gate G-G, fail-closed). El disparador d'avaluació és EXTERN.
RUNNER_ACTIU = False

# Conjunt TANCAT d'operadors de comparació (cap és codi arbitrari → INV-1).
_OPS = {
    ">=": operator.ge, "<=": operator.le, "==": operator.eq,
    "!=": operator.ne, ">": operator.gt, "<": operator.lt,
}


@dataclass(frozen=True)
class TriggerCondicio:
    camp: str       # clau dins l'snapshot d'observacions
    op: str         # ∈ _OPS
    valor: float    # literal numèric


@dataclass(frozen=True)
class SignedTrigger:
    id: str
    playbook_id: str
    condicio: TriggerCondicio
    params: dict = field(default_factory=dict)


class SignedTriggerCatalog:
    def __init__(self, triggers: dict[str, SignedTrigger], *, fingerprint: str | None = None) -> None:
        self._t = dict(triggers)
        self.fingerprint = fingerprint

    def __contains__(self, tid: str) -> bool:
        return tid in self._t

    def get(self, tid: str) -> SignedTrigger | None:
        return self._t.get(tid)

    def require(self, tid: str) -> SignedTrigger:
        t = self._t.get(tid)
        if t is None:
            raise TriggerError(f"Trigger «{tid}» FORA del catàleg signat")
        return t

    @property
    def triggers(self) -> tuple[SignedTrigger, ...]:
        return tuple(self._t.values())

    @property
    def ids(self) -> set[str]:
        return set(self._t)


def _parse_condicio(tid: str, raw: dict) -> TriggerCondicio:
    camp = str(raw.get("camp", "")).strip()
    if not camp:
        raise TriggerError(f"Trigger «{tid}»: condició sense camp")
    op = str(raw.get("op", "")).strip()
    if op not in _OPS:
        raise TriggerError(f"Trigger «{tid}»: operador «{op}» no permès (només {sorted(_OPS)})")
    try:
        valor = float(raw["valor"])
    except (KeyError, ValueError, TypeError) as exc:
        raise TriggerError(f"Trigger «{tid}»: valor de condició absent o no numèric") from exc
    # No-finits (nan/inf) prohibits: amb `nan` el comparador «!=» dispararia SEMPRE i «==»
    # MAI (semàntica IEEE-754) → un trigger amb condició enganyosa (red-team F5, fail-closed).
    if not math.isfinite(valor):
        raise TriggerError(f"Trigger «{tid}»: valor de condició no finit (nan/inf) no permès")
    return TriggerCondicio(camp=camp, op=op, valor=valor)


def load_signed_triggers(*, data_path: str, sig_path: str, pubkey_path: str,
                         playbooks: SignedPlaybookCatalog,
                         gnupghome: str | None = None, verify: bool = True,
                         expected_fingerprint: str | None = None) -> SignedTriggerCatalog:
    """Carrega els triggers signats (GPG amb pinning) i els valida encreuadament:
    cada trigger referencia un `playbook` del catàleg signat i una condició vàlida."""
    fingerprint = None
    if verify:
        fingerprint = verify_gpg_signature(
            data_path=data_path, sig_path=sig_path, pubkey_path=pubkey_path, gnupghome=gnupghome,
            expected_fingerprint=expected_fingerprint or fingerprint_de_confianca(),
        )
    raw = pathlib.Path(data_path).read_text(encoding="utf-8")
    try:
        doc = strictyaml.load(raw).data
    except Exception as exc:  # noqa: BLE001
        raise TriggerError(f"Triggers YAML invàlid: {exc}") from exc

    triggers: dict[str, SignedTrigger] = {}
    for entry in doc.get("triggers", []) or []:
        tid = str(entry["id"])
        pid = str(entry["playbook"])
        if pid not in playbooks:
            raise TriggerError(f"Trigger «{tid}»: playbook «{pid}» FORA del catàleg signat")
        cond = _parse_condicio(tid, dict(entry.get("condicio", {}) or {}))
        triggers[tid] = SignedTrigger(id=tid, playbook_id=pid, condicio=cond,
                                      params=dict(entry.get("params", {}) or {}))
    if not triggers:
        raise TriggerError("Catàleg de triggers buit o sense secció 'triggers'")
    return SignedTriggerCatalog(triggers, fingerprint=fingerprint)


def avalua(trigger: SignedTrigger, snapshot: dict) -> bool:
    """Cert si la condició del trigger es compleix sobre l'snapshot. Funció PURA.

    Fail-closed: camp absent → False (no es dispara sense dada); valor no numèric/booleà
    → TriggerError (el CORE no compara dades lliures, possible PII)."""
    cond = trigger.condicio
    if cond.camp not in (snapshot or {}):
        return False  # sense observació del camp → el trigger NO es dispara
    v = snapshot[cond.camp]
    if isinstance(v, bool) or isinstance(v, (int, float)):
        fv = float(v)
        # Observació no finita (nan/inf) → fail-closed: el trigger NO es dispara (cap
        # comparació amb nan és fiable; evita un dispar fantasma per dada corrupta).
        if not math.isfinite(fv):
            return False
        return bool(_OPS[cond.op](fv, cond.valor))
    raise TriggerError(
        f"Trigger «{trigger.id}»: l'observació «{cond.camp}» no és numèrica/booleana "
        f"({type(v).__name__}); el CORE no compara dades lliures")


def triggers_actius(catalog: SignedTriggerCatalog, snapshot: dict) -> list[SignedTrigger]:
    """Triggers la condició dels quals es compleix ARA (funció PURA; no proposa ni executa)."""
    return [t for t in catalog.triggers if avalua(t, snapshot)]


@dataclass(frozen=True)
class PropostaTrigger:
    trigger_id: str
    plan: Plan
    requests: tuple[ApprovalRequest, ...]


def materialitza_proposta_trigger(trigger: SignedTrigger, *, playbooks: SignedPlaybookCatalog,
                                  allowlist: SignedAllowlist, gate: ApprovalGate,
                                  session, _now: float | None = None) -> PropostaTrigger:
    """PROPOSE-ONLY: instancia el playbook del trigger en un Plan i ENCUA una proposta
    d'aprovació per pas. NO executa res (cap invoke/run): un humà ha d'aprovar abans."""
    pb = playbooks.require(trigger.playbook_id)
    plan = instantiate(pb, trigger.params)
    requests: list[ApprovalRequest] = []
    for step in plan.steps:
        eina = allowlist.require(step.tool_id)
        requests.append(gate.propose(
            session=session, tool_id=step.tool_id, risk=eina.risk,
            args=step.args, descripcio=eina.descripcio, _now=_now))
    return PropostaTrigger(trigger_id=trigger.id, plan=plan, requests=tuple(requests))
