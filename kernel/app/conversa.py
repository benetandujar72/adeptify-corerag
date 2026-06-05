"""K16·F5d — Bucle conversacional PROPOSE → CONFIRM (humà al bucle, sense execució nova).

És la "cara conversacional" del kernel, però NO afegeix cap via d'execució (INV-1): només
encadena peces que ja existeixen i estan provades:

    text NL ──IntentResolver(F5a)──► playbook_id ∈ catàleg SIGNAT (ENUM tancat, INV-4)
            ──instantiate(K10)─────► Plan finit (params tipats + guarda PII, G-I)
            ──ApprovalGate.propose(K6)──► ApprovalRequest(s) PENDING (resum NL determinista)
            ──MemoriaTasques(F5b)──► TascaAutomatitzada(PROPOSADA)

`proposa()` NO executa res: deixa una tasca PROPOSADA i unes peticions d'aprovació. Perquè
s'executi, un HUMÀ ha d'aprovar (gate.approve → tokens) i després cridar `confirma()` amb
els tokens. `confirma()` delega al MATEIX `Orchestrator.run` (RBAC→ApprovalGate→esquema→
callable pre-registrat): la decisió de QUÈ s'executa mai surt de l'artefacte signat ni de
la compuerta humana. Si falta cap aprovació, l'orquestrador ESCALA i no s'executa res; la
tasca segueix PROPOSADA (reintentable). Només quan el Pla s'ha completat passa a EXECUTADA.

NO es desa MAI el text NL en brut (pot dur PII): de la conversa només en queda el
`playbook_id` + params (ja sanejats). La frontera PII es comprova al resolutor (F5a) i a
`instantiate`/`MemoriaTasques` (defensa en profunditat, G-I).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .approval import ApprovalGate, ApprovalRequest, requereix_aprovacio
from .allowlist import SignedAllowlist
from .intent import IntentResolver, IntentResult
from .orchestrator import Orchestrator, Plan, RunResult
from .playbooks import SignedPlaybookCatalog, instantiate
from .task_memory import MemoriaTasques, TascaAutomatitzada


class EstatProposta(str, Enum):
    PROPOSAT = "proposat"        # intenció resolta → tasca PROPOSADA + aprovacions pendents
    AMBIGU = "ambigu"            # diversos playbooks empaten → cal desambiguació humana
    CAP = "cap"                  # cap playbook del catàleg coincideix
    REBUTJAT_PII = "rebutjat_pii"  # el text duia PII evident → no s'ha processat (G-I)


@dataclass(frozen=True)
class ResultatProposta:
    """Resultat de `proposa()`. Si `estat != PROPOSAT`, NO hi ha tasca ni aprovacions
    (res s'ha materialitzat ni encuat): la capa de presentació demana a l'humà que
    reformuli o triï de `intent.candidates` (sempre dins del catàleg signat)."""
    estat: EstatProposta
    intent: IntentResult
    tasca: TascaAutomatitzada | None = None
    plan: Plan | None = None
    requests: tuple[ApprovalRequest, ...] = ()


@dataclass(frozen=True)
class ResultatConfirmacio:
    """Resultat de `confirma()`. `executat` és cert només si el Pla s'ha completat."""
    executat: bool
    run: RunResult
    tasca: TascaAutomatitzada | None = None


class BuclePropose:
    """Orquestra propose→confirm. NO és una via d'execució: `confirma()` delega a
    l'`Orchestrator` que se li passa. Totes les peces (catàleg, allowlist, gate) han de
    ser SIGNADES/compartides amb el `ToolKernel` de l'orquestrador perquè els tokens casin."""

    def __init__(self, *, catalog: SignedPlaybookCatalog, allowlist: SignedAllowlist,
                 gate: ApprovalGate, resolver: IntentResolver, memoria: MemoriaTasques) -> None:
        self._catalog = catalog
        self._allowlist = allowlist
        self._gate = gate
        self._resolver = resolver
        self._memoria = memoria

    # ── PROPOSE: NL → tasca PROPOSADA + aprovacions pendents (sense executar) ──
    def proposa(self, *, session: Any, text_nl: str,
                params: Mapping[str, Any] | None = None,
                _now: float | None = None) -> ResultatProposta:
        intent = self._resolver.resol(text_nl)
        if intent.refusat_pii:
            return ResultatProposta(EstatProposta.REBUTJAT_PII, intent)
        if intent.match is None:
            estat = EstatProposta.AMBIGU if intent.ambigu else EstatProposta.CAP
            return ResultatProposta(estat, intent)

        # L'ENUM tancat garanteix que match ∈ catàleg; require() és la xarxa de seguretat.
        pb = self._catalog.require(intent.match)
        # Params EXPLÍCITS i tipats (mai del text lliure): instantiate valida tipus i PII.
        plan = instantiate(pb, dict(params or {}))

        # Encua una proposta d'aprovació NOMÉS per als passos de risc ≥2 (write-local o
        # superior): els passos info/read no requereixen aprovació humana (K6.1) i una
        # petició de «0 aprovacions» seria soroll. Els passos de risc igualment passen pel
        # RBAC a l'invoke (INV-2).
        requests: list[ApprovalRequest] = []
        for step in plan.steps:
            eina = self._allowlist.require(step.tool_id)
            if requereix_aprovacio(eina.risk):
                requests.append(self._gate.propose(
                    session=session, tool_id=step.tool_id, risk=eina.risk,
                    args=step.args, descripcio=eina.descripcio, _now=_now))

        # Recorda la proposta (sense PII, sense text NL en brut): playbook_id + params.
        tasca = self._memoria.registra_proposta(
            session=session, playbook_id=pb.id, params=dict(params or {}), _now=_now)
        return ResultatProposta(EstatProposta.PROPOSAT, intent, tasca=tasca,
                                plan=plan, requests=tuple(requests))

    # ── CONFIRM: amb els tokens humans, delega a Orchestrator.run (sense via nova) ──
    def confirma(self, *, session: Any, tasca_id: str, orchestrator: Orchestrator,
                 approvals: Mapping[str, str] | None = None,
                 _now: float | None = None) -> ResultatConfirmacio:
        # Guard ABANS d'executar: propietari + encara PROPOSADA (mai la tasca d'una altra
        # sessió, mai reexecutar una de decidida). Si falla, no s'executa res.
        tasca = self._memoria.requereix_pendent_de(tasca_id, session=session)
        pb = self._catalog.require(tasca.playbook_id)
        plan = instantiate(pb, tasca.params)  # re-materialitza determinista (no es fia d'un Plan desat)

        run = orchestrator.run(session, plan, approvals)

        if run.completed:
            # Esdeveniment humà CONFIRMAT i, com que el Pla s'ha completat, EXECUTAT.
            self._memoria.confirma(tasca_id, session=session, _now=_now)
            self._memoria.marca_executada(tasca_id, session=session, _now=_now)
        # Si NO s'ha completat (escalat per manca d'aprovació, o error d'una eina), la
        # tasca segueix PROPOSADA: l'humà recull els tokens que falten i reintenta confirmar.
        return ResultatConfirmacio(executat=run.completed, run=run,
                                   tasca=self._memoria.get(tasca_id))

    # ── Rebuig explícit d'una proposta per l'humà ──
    def rebutja(self, *, session: Any, tasca_id: str,
                _now: float | None = None) -> TascaAutomatitzada:
        return self._memoria.rebutja(tasca_id, session=session, _now=_now)
