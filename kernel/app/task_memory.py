"""K14·F5b — Memòria de tasques automatitzades (propose → confirm → execute).

Registre del CICLE DE VIDA d'una tasca proposada per la capa conversacional (F5). NO
és cap via d'execució: només recorda l'estat (proposada/confirmada/executada/rebutjada)
perquè un humà pugui confirmar més tard el que es va proposar. L'execució real sempre
passa pel mateix `Orchestrator.run` (INV-1) i la compuerta d'aprovació (K6).

Garanties (fail-closed):

- **Màquina d'estats estricta.** Només transicions vàlides: PROPOSADA→{CONFIRMADA,REBUTJADA},
  CONFIRMADA→EXECUTADA. Qualsevol altra (p. ex. executar sense confirmar, o reobrir una
  tasca terminal) llança `TascaError`. Mai s'executa el que no s'ha confirmat.
- **Propietari lligat (anti confused-deputy).** Cada tasca recorda la sessió i el tenant
  que la van proposar; confirmar/executar/rebutjar exigeix la MATEIXA (session_id, tenant_id).
  Una sessió no pot confirmar la proposta d'una altra.
- **Id determinista i idempotent.** `tasca_id = sha256(session, tenant, playbook, params)`:
  reproposar el mateix retorna la MATEIXA tasca pendent (no en duplica), però reproposar
  una tasca ja decidida es rebutja.
- **Frontera PII (defensa en profunditat, G-I).** Es rebutja desar params amb PII evident,
  amb el MATEIX detector que els playbooks (encara que `instantiate` ja l'hagi comprovat).
- **Sense PII al registre.** Es desa `playbook_id` + params (ja sanejats); cap nom/text lliure.

Model de concurrència: igual que la resta del kernel (monofil, sense runner de fons; gates
G-A/G-G). Les transicions són comprova-i-fixa; no hi ha cap bucle async que hi competeixi.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .errors import TascaError
from .playbooks import conte_pii_evident


class EstatTasca(str, Enum):
    PROPOSADA = "proposada"
    CONFIRMADA = "confirmada"
    EXECUTADA = "executada"
    REBUTJADA = "rebutjada"


# Transicions PERMESES (fail-closed: tota la resta es rebutja). Els estats terminals
# (EXECUTADA, REBUTJADA) no tenen successors.
_TRANSICIONS: dict[EstatTasca, frozenset[EstatTasca]] = {
    EstatTasca.PROPOSADA: frozenset({EstatTasca.CONFIRMADA, EstatTasca.REBUTJADA}),
    EstatTasca.CONFIRMADA: frozenset({EstatTasca.EXECUTADA}),
    EstatTasca.EXECUTADA: frozenset(),
    EstatTasca.REBUTJADA: frozenset(),
}


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def tasca_id(*, session_id: str, tenant_id: str, playbook_id: str,
             params: Mapping[str, Any]) -> str:
    """Id DETERMINISTA d'una tasca (lligat a sessió+tenant+playbook+params).

    Mateixa proposta → mateix id (idempotent); propostes diferents → ids diferents."""
    core = {"session_id": session_id, "tenant_id": tenant_id,
            "playbook_id": playbook_id, "params": dict(params or {})}
    return hashlib.sha256(_canonical(core).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TascaAutomatitzada:
    """Instantània IMMUTABLE de l'estat d'una tasca. La mutació només passa per la
    `MemoriaTasques` (que en crea una de nova); el registre en si no es muta."""
    tasca_id: str
    session_id: str
    tenant_id: str
    playbook_id: str
    params: dict = field(default_factory=dict)
    estat: EstatTasca = EstatTasca.PROPOSADA
    creada_utc: float = 0.0
    actualitzada_utc: float = 0.0

    @property
    def terminal(self) -> bool:
        return not _TRANSICIONS[self.estat]


def _comprova_pii(playbook_id: str, params: Mapping[str, Any]) -> None:
    for clau, valor in (params or {}).items():
        # Valors NIATS (dict/list/tuple) no permesos: el detector de PII inspecciona
        # escalars; un nivell d'indirecció amagaria PII dins (mateixa defensa que els
        # playbooks, red-team F5). Els params de playbook són tipats (escalars) per disseny.
        if isinstance(valor, (dict, list, tuple)):
            raise TascaError(
                f"Tasca «{playbook_id}»: el param «{clau}» és niat (dict/list); no permès")
        if conte_pii_evident(valor):
            raise TascaError(
                f"Tasca «{playbook_id}»: el param «{clau}» sembla contenir PII evident; "
                "el CORE no desa PII (frontera transversal)")


class MemoriaTasques:
    """Magatzem en memòria del cicle de vida de tasques (single-thread, fail-closed)."""

    def __init__(self) -> None:
        self._t: dict[str, TascaAutomatitzada] = {}

    def _now(self, _now: float | None = None) -> float:
        return _now if _now is not None else time.time()

    # ── Registre d'una proposta (idempotent per id determinista) ──
    def registra_proposta(self, *, session: Any, playbook_id: str,
                          params: Mapping[str, Any] | None = None,
                          _now: float | None = None) -> TascaAutomatitzada:
        ctx = session.context
        params = dict(params or {})
        _comprova_pii(playbook_id, params)  # G-I: cap PII al registre
        tid = tasca_id(session_id=ctx.session_id, tenant_id=ctx.tenant_id,
                       playbook_id=playbook_id, params=params)
        existent = self._t.get(tid)
        if existent is not None:
            # Reproposar una tasca encara PENDENT és idempotent (retorna la mateixa);
            # reproposar-ne una de JA DECIDIDA es rebutja (fail-closed: no es reobre).
            if existent.estat is EstatTasca.PROPOSADA:
                return existent
            raise TascaError(
                f"Tasca «{tid[:12]}…» ja existeix en estat «{existent.estat.value}»; "
                "no es pot reproposar una tasca ja decidida")
        ara = self._now(_now)
        tasca = TascaAutomatitzada(
            tasca_id=tid, session_id=ctx.session_id, tenant_id=ctx.tenant_id,
            playbook_id=playbook_id, params=params, estat=EstatTasca.PROPOSADA,
            creada_utc=ara, actualitzada_utc=ara)
        self._t[tid] = tasca
        return tasca

    def get(self, tid: str) -> TascaAutomatitzada | None:
        return self._t.get(tid)

    def requereix(self, tid: str) -> TascaAutomatitzada:
        t = self._t.get(tid)
        if t is None:
            raise TascaError(f"Tasca «{tid[:12]}…» inexistent")
        return t

    def llista(self, *, estat: EstatTasca | None = None) -> tuple[TascaAutomatitzada, ...]:
        vals = tuple(self._t.values())
        return vals if estat is None else tuple(t for t in vals if t.estat is estat)

    def requereix_pendent_de(self, tid: str, *, session: Any) -> TascaAutomatitzada:
        """Guard SENSE mutació: retorna la tasca si existeix, és del propietari (sessió+
        tenant) i encara està PROPOSADA; si no, llança. El crida el bucle propose→confirm
        ABANS d'executar res, perquè cap sessió executi la proposta d'una altra (confused-
        deputy) ni es reexecuti una tasca ja decidida."""
        t = self.requereix(tid)
        ctx = session.context
        if ctx.session_id != t.session_id or ctx.tenant_id != t.tenant_id:
            raise TascaError(
                f"Tasca «{tid[:12]}…»: la sessió «{ctx.session_id}»/«{ctx.tenant_id}» no és "
                "la propietària (confused-deputy)")
        if t.estat is not EstatTasca.PROPOSADA:
            raise TascaError(
                f"Tasca «{tid[:12]}…»: no està PROPOSADA (és «{t.estat.value}»); res a confirmar")
        return t

    # ── Transició genèrica amb comprovació de propietari i de legalitat ──
    def _transiciona(self, tid: str, nou: EstatTasca, *, session: Any,
                     _now: float | None = None) -> TascaAutomatitzada:
        actual = self.requereix(tid)
        ctx = session.context
        # Anti confused-deputy: només el propietari (sessió+tenant) pot fer la transició.
        if ctx.session_id != actual.session_id or ctx.tenant_id != actual.tenant_id:
            raise TascaError(
                f"Tasca «{tid[:12]}…»: la sessió «{ctx.session_id}»/«{ctx.tenant_id}» no és "
                "la propietària; no pot canviar-ne l'estat (confused-deputy)")
        if nou not in _TRANSICIONS[actual.estat]:
            raise TascaError(
                f"Tasca «{tid[:12]}…»: transició il·legal {actual.estat.value}→{nou.value}")
        actualitzada = TascaAutomatitzada(
            tasca_id=actual.tasca_id, session_id=actual.session_id, tenant_id=actual.tenant_id,
            playbook_id=actual.playbook_id, params=actual.params, estat=nou,
            creada_utc=actual.creada_utc, actualitzada_utc=self._now(_now))
        self._t[tid] = actualitzada
        return actualitzada

    def confirma(self, tid: str, *, session: Any, _now: float | None = None) -> TascaAutomatitzada:
        return self._transiciona(tid, EstatTasca.CONFIRMADA, session=session, _now=_now)

    def rebutja(self, tid: str, *, session: Any, _now: float | None = None) -> TascaAutomatitzada:
        return self._transiciona(tid, EstatTasca.REBUTJADA, session=session, _now=_now)

    def marca_executada(self, tid: str, *, session: Any,
                        _now: float | None = None) -> TascaAutomatitzada:
        return self._transiciona(tid, EstatTasca.EXECUTADA, session=session, _now=_now)
