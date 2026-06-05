"""K11 (F4) — Scheduler de tasques programades, en mode PROPOSE-ONLY.

Decisió de disseny (gates G-A/G-B resolts): el kernel NO té cap runner de fons ni
bucle async; tampoc cap dependència de cron (`croniter`). Aquest mòdul:

1. Calcula de forma DETERMINISTA quines tasques toquen (`is_due`/`tasques_due`) amb
   aritmètica pròpia sobre intervals i hores UTC (sense dep nova).
2. Materialitza la proposta d'una tasca: instancia el playbook signat → `Plan`
   (K10) i ENCUA una proposta d'aprovació per CADA pas via l'ApprovalGate (K6).
   MAI executa res: no toca `ToolKernel.invoke` ni `Orchestrator.run`.

El disparador temporal és EXTERN (un cron d'OPS que crida un punt gateado); aquí
no hi ha cap procés autònom. `RUNNER_ACTIU = False` ho deixa explícit (fail-closed):
cap execució automàtica sense un humà al bucle (INV-1: cap via d'execució nova).
"""

from __future__ import annotations

import datetime as dt
import pathlib
from dataclasses import dataclass, field

import strictyaml

from .allowlist import SignedAllowlist, fingerprint_de_confianca, verify_gpg_signature
from .approval import ApprovalGate, ApprovalRequest
from .errors import SchedulerError
from .orchestrator import Plan
from .playbooks import SignedPlaybookCatalog, instantiate

# Cap runner de fons al kernel (gate G-G, fail-closed). El disparador és extern.
RUNNER_ACTIU = False

_TIPUS_SPEC = {"interval", "diari", "setmanal"}


def _valida_spec(tid: str, spec: dict) -> None:
    """Valida els camps d'una spec a la CÀRREGA (fail-closed): cap artefacte signat
    malformat passa, i is_due mai veu camps absents/fora de rang (red-team F4)."""
    tipus = spec.get("tipus")
    if tipus not in _TIPUS_SPEC:
        raise SchedulerError(f"Tasca «{tid}»: schedule.tipus invàlid «{tipus}»")
    if tipus == "interval":
        try:
            seg = float(spec["segons"])
        except (KeyError, ValueError, TypeError) as exc:
            raise SchedulerError(f"Tasca «{tid}»: interval.segons absent o invàlid") from exc
        if seg <= 0:
            raise SchedulerError(f"Tasca «{tid}»: interval.segons ha de ser > 0")
        return
    try:
        h, m = int(spec["hora"]), int(spec["minut"])
    except (KeyError, ValueError, TypeError) as exc:
        raise SchedulerError(f"Tasca «{tid}»: hora/minut absents o invàlids") from exc
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise SchedulerError(f"Tasca «{tid}»: hora/minut fora de rang")
    if tipus == "setmanal":
        try:
            d = int(spec["dia"])
        except (KeyError, ValueError, TypeError) as exc:
            raise SchedulerError(f"Tasca «{tid}»: dia absent o invàlid") from exc
        if not (0 <= d <= 6):
            raise SchedulerError(f"Tasca «{tid}»: dia fora de rang (0-6)")


def _dt_utc(ts: float) -> dt.datetime:
    return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)


def _objectiu_diari(ara: dt.datetime, hora: int, minut: int) -> dt.datetime:
    obj = ara.replace(hour=hora, minute=minut, second=0, microsecond=0)
    return obj if obj <= ara else obj - dt.timedelta(days=1)


def _objectiu_setmanal(ara: dt.datetime, dia: int, hora: int, minut: int) -> dt.datetime:
    obj = ara.replace(hour=hora, minute=minut, second=0, microsecond=0)
    obj -= dt.timedelta(days=(ara.weekday() - dia) % 7)  # retrocedeix al weekday demanat
    return obj if obj <= ara else obj - dt.timedelta(days=7)


def is_due(spec: dict, *, last_fire: float | None, now: float) -> bool:
    """Cert si la tasca toca ARA (UTC), donat l'últim tret. Determinista, sense dep.

    - interval: toca si no s'ha tret mai o han passat ≥ `segons` des de l'últim tret.
    - diari/setmanal: toca si l'últim objectiu (hora UTC) ≤ ara i no s'ha tret des d'ell.
    """
    tipus = spec.get("tipus")
    if tipus == "interval":
        seg = float(spec["segons"])
        if seg <= 0:
            raise SchedulerError("interval.segons ha de ser > 0")
        return last_fire is None or (now - last_fire) >= seg
    ara = _dt_utc(now)
    if tipus == "diari":
        objectiu = _objectiu_diari(ara, int(spec["hora"]), int(spec["minut"]))
    elif tipus == "setmanal":
        objectiu = _objectiu_setmanal(ara, int(spec["dia"]), int(spec["hora"]), int(spec["minut"]))
    else:
        raise SchedulerError(f"tipus de schedule desconegut: {tipus!r}")
    if ara < objectiu:
        return False
    return last_fire is None or _dt_utc(last_fire) < objectiu


@dataclass(frozen=True)
class ScheduledTask:
    id: str
    playbook_id: str
    params: dict = field(default_factory=dict)
    spec: dict = field(default_factory=dict)


class SignedScheduleCatalog:
    def __init__(self, tasques: dict[str, ScheduledTask], *, fingerprint: str | None = None) -> None:
        self._t = dict(tasques)
        self.fingerprint = fingerprint

    def __contains__(self, tid: str) -> bool:
        return tid in self._t

    def get(self, tid: str) -> ScheduledTask | None:
        return self._t.get(tid)

    @property
    def tasques(self) -> tuple[ScheduledTask, ...]:
        return tuple(self._t.values())

    @property
    def ids(self) -> set[str]:
        return set(self._t)


def load_signed_schedule(*, data_path: str, sig_path: str, pubkey_path: str,
                         playbooks: SignedPlaybookCatalog,
                         gnupghome: str | None = None, verify: bool = True,
                         expected_fingerprint: str | None = None) -> SignedScheduleCatalog:
    """Carrega el calendari signat (GPG amb pinning) i el valida de forma encreuada:
    cada tasca referencia un `playbook` del catàleg signat i un `schedule` vàlid."""
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
        raise SchedulerError(f"Schedule YAML invàlid: {exc}") from exc

    tasques: dict[str, ScheduledTask] = {}
    for entry in doc.get("tasques", []) or []:
        tid = str(entry["id"])
        pid = str(entry["playbook"])
        if pid not in playbooks:
            raise SchedulerError(f"Tasca «{tid}»: playbook «{pid}» FORA del catàleg signat")
        spec = dict(entry.get("schedule", {}) or {})
        _valida_spec(tid, spec)  # fail-closed: tipus + camps presents i en rang
        tasques[tid] = ScheduledTask(id=tid, playbook_id=pid,
                                     params=dict(entry.get("params", {}) or {}), spec=spec)
    if not tasques:
        raise SchedulerError("Calendari buit o sense secció 'tasques'")
    return SignedScheduleCatalog(tasques, fingerprint=fingerprint)


def tasques_due(catalog: SignedScheduleCatalog, *, now: float,
                ultim_tret: dict[str, float] | None = None) -> list[ScheduledTask]:
    """Tasques que toquen ARA (funció PURA; no executa ni proposa res)."""
    ultim = ultim_tret or {}
    return [t for t in catalog.tasques if is_due(t.spec, last_fire=ultim.get(t.id), now=now)]


@dataclass(frozen=True)
class PropostaTasca:
    task_id: str
    plan: Plan
    requests: tuple[ApprovalRequest, ...]


def materialitza_proposta(task: ScheduledTask, *, playbooks: SignedPlaybookCatalog,
                          allowlist: SignedAllowlist, gate: ApprovalGate,
                          session, _now: float | None = None) -> PropostaTasca:
    """PROPOSE-ONLY: instancia el playbook de la tasca en un Plan i ENCUA una proposta
    d'aprovació per cada pas (ApprovalGate.propose). NO executa res (cap invoke/run):
    un humà ha d'aprovar abans que res s'executi, perquè al disparar no hi ha humà present."""
    pb = playbooks.require(task.playbook_id)
    plan = instantiate(pb, task.params)
    requests: list[ApprovalRequest] = []
    for step in plan.steps:
        eina = allowlist.require(step.tool_id)
        requests.append(gate.propose(
            session=session, tool_id=step.tool_id, risk=eina.risk,
            args=step.args, descripcio=eina.descripcio, _now=_now,
        ))
    return PropostaTasca(task_id=task.id, plan=plan, requests=tuple(requests))
