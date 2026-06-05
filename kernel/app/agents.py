"""K13 (F4) — Multi-agent coordinat per DEFINICIÓ SIGNADA (nucli d'INV-4).

INV-4 (la invariant més delicada per a un sistema tipus OpenClaw): cap agent
instancia/modifica/elimina agents en runtime. Aquí, els agents són definicions
DECLARATIVES PRE-APROVADES i SIGNADES (mateix patró que l'allowlist K3.1 i els
playbooks K10), i la coordinació entre ells ve EXCLUSIVAMENT d'un graf signat:

- K13.1 `SignedAgentRegistry`: registre immutable d'agents (frozen, SENSE cap API de
  creació/clonatge en runtime). Validació encreuada: les eines/playbooks permesos
  de cada agent ∈ allowlist/catàleg signats.
- K13.2 `Coordinador`: el graf de col·laboració (handoffs) ve d'un artefacte signat.
  Es valida a boot (agent ∈ registre, SENSE cicles, ≤ límit de handoffs). Cada node
  s'executa en una Session amb `session_id` ÚNIC i NO reutilitzat (anti confused-deputy);
  el RBAC s'aplica amb el role propi de cada agent. El coordinador NO és una via
  d'execució nova: cada node passa pel mateix `Orchestrator.run` (RBAC→ApprovalGate→…).
- K13.3 canal entre agents: els missatges són DADES NO executables (reús de
  guardrails K7.2 `wrap_untrusted` + `detect_injection`); mai instruccions.

Aquest mòdul NO executa codi arbitrari (INV-1): només valida grafs i construeix Sessions.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

import strictyaml

from .allowlist import SignedAllowlist, fingerprint_de_confianca, verify_gpg_signature
from .errors import AgentDefError
from .guardrails import detect_injection, wrap_untrusted
from .playbooks import SignedPlaybookCatalog
from .session import Budget, Deadline, ImmutableContext, Session

# Límit dur de handoffs en una col·laboració (defensa anti-explosió; INV-4/K1.2).
MAX_HANDOFFS = 20


@dataclass(frozen=True)
class AgentDef:
    """Definició declarativa d'un agent (immutable). NO es crea ni es muta en runtime."""
    id: str
    role: str
    allowed_tools: frozenset[str] = frozenset()
    allowed_playbooks: frozenset[str] = frozenset()
    descripcio: str = ""


class SignedAgentRegistry:
    """Registre IMMUTABLE d'agents signats. Deliberadament SENSE cap mètode públic
    de creació/registre/clonatge en runtime: tota la definició ve de l'artefacte signat."""

    def __init__(self, agents: dict[str, AgentDef], *, fingerprint: str | None = None) -> None:
        self._a = dict(agents)
        self.fingerprint = fingerprint

    def __contains__(self, agent_id: str) -> bool:
        return agent_id in self._a

    def get(self, agent_id: str) -> AgentDef | None:
        return self._a.get(agent_id)

    def require(self, agent_id: str) -> AgentDef:
        a = self._a.get(agent_id)
        if a is None:
            raise AgentDefError(f"Agent «{agent_id}» FORA del registre signat (INV-4)")
        return a

    @property
    def ids(self) -> set[str]:
        return set(self._a)


def _llista(valor) -> list[str]:
    if not valor:
        return []
    if isinstance(valor, str):
        return [valor]
    return [str(v) for v in valor]


def load_signed_agents(*, data_path: str, sig_path: str, pubkey_path: str,
                       allowlist: SignedAllowlist, playbooks: SignedPlaybookCatalog,
                       gnupghome: str | None = None, verify: bool = True,
                       expected_fingerprint: str | None = None) -> SignedAgentRegistry:
    """Carrega el registre d'agents (GPG amb pinning) i el valida de forma encreuada:
    cada eina permesa ∈ allowlist signada; cada playbook permès ∈ catàleg signat."""
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
        raise AgentDefError(f"Agents YAML invàlid: {exc}") from exc

    agents: dict[str, AgentDef] = {}
    for entry in doc.get("agents", []) or []:
        aid = str(entry["id"])
        role = str(entry.get("role", "")).strip()
        if not role:
            raise AgentDefError(f"Agent «{aid}»: role buit")
        tools = _llista(entry.get("allowed_tools"))
        pbs = _llista(entry.get("allowed_playbooks"))
        for t in tools:
            if t not in allowlist:
                raise AgentDefError(f"Agent «{aid}»: eina permesa «{t}» FORA de l'allowlist signada")
        for p in pbs:
            if p not in playbooks:
                raise AgentDefError(f"Agent «{aid}»: playbook permès «{p}» FORA del catàleg signat")
        agents[aid] = AgentDef(id=aid, role=role, allowed_tools=frozenset(tools),
                               allowed_playbooks=frozenset(pbs),
                               descripcio=str(entry.get("descripcio", "")))
    if not agents:
        raise AgentDefError("Registre d'agents buit o sense secció 'agents'")
    return SignedAgentRegistry(agents, fingerprint=fingerprint)


# ── K13.2 · Graf de col·laboració signat ─────────────────────────────────────
@dataclass(frozen=True)
class CollabNode:
    agent_id: str
    playbook_id: str
    seguents: tuple[str, ...] = ()


@dataclass(frozen=True)
class Collaboracio:
    id: str
    inici: str
    nodes: dict[str, CollabNode] = field(default_factory=dict)


def _detecta_cicle(nodes: dict[str, CollabNode], inici: str) -> None:
    """DFS amb detecció de cicle (back-edge) i de referències a nodes inexistents."""
    estat: dict[str, int] = {}  # 0=no vist, 1=en progrés, 2=fet

    def visita(n: str) -> None:
        if n not in nodes:
            raise AgentDefError(f"Col·laboració: node «{n}» referenciat però no definit")
        if estat.get(n) == 1:
            raise AgentDefError(f"Col·laboració: CICLE detectat al graf (node «{n}») — prohibit (INV-4)")
        if estat.get(n) == 2:
            return
        estat[n] = 1
        for seg in nodes[n].seguents:
            visita(seg)
        estat[n] = 2

    visita(inici)


def load_signed_collaboracions(*, data_path: str, sig_path: str, pubkey_path: str,
                               agents: SignedAgentRegistry, playbooks: SignedPlaybookCatalog,
                               gnupghome: str | None = None, verify: bool = True,
                               expected_fingerprint: str | None = None) -> dict[str, Collaboracio]:
    """Carrega els grafs de col·laboració signats i els valida (agents∈registre,
    playbooks permesos per l'agent, SENSE cicles, ≤ MAX_HANDOFFS)."""
    if verify:
        verify_gpg_signature(
            data_path=data_path, sig_path=sig_path, pubkey_path=pubkey_path, gnupghome=gnupghome,
            expected_fingerprint=expected_fingerprint or fingerprint_de_confianca(),
        )
    raw = pathlib.Path(data_path).read_text(encoding="utf-8")
    try:
        doc = strictyaml.load(raw).data
    except Exception as exc:  # noqa: BLE001
        raise AgentDefError(f"Col·laboracions YAML invàlid: {exc}") from exc

    collabs: dict[str, Collaboracio] = {}
    for entry in doc.get("collaboracions", []) or []:
        cid = str(entry["id"])
        nodes: dict[str, CollabNode] = {}
        for nd in entry.get("nodes", []) or []:
            aid = str(nd["agent"])
            if aid in nodes:  # el model identifica node==agent: cap agent dues vegades (fail-closed)
                raise AgentDefError(f"Col·laboració «{cid}»: agent «{aid}» duplicat als nodes")
            agent = agents.require(aid)               # agent ∈ registre signat (INV-4)
            pid = str(nd["playbook"])
            if pid not in agent.allowed_playbooks:
                raise AgentDefError(
                    f"Col·laboració «{cid}»: l'agent «{aid}» no té permès el playbook «{pid}»")
            if pid not in playbooks:
                raise AgentDefError(f"Col·laboració «{cid}»: playbook «{pid}» FORA del catàleg signat")
            # Least-privilege (INV-2): si l'agent declara allowed_tools, TOTES les eines
            # del playbook han d'estar dins el seu scope (no pot executar eines fora d'ell).
            pb = playbooks.require(pid)
            if agent.allowed_tools:
                for s in pb.passos:
                    if s.tool_id not in agent.allowed_tools:
                        raise AgentDefError(
                            f"Col·laboració «{cid}»: el playbook «{pid}» usa l'eina «{s.tool_id}» "
                            f"FORA de l'scope d'eines de l'agent «{aid}»")
            seg = tuple(_llista(nd.get("seguents")))
            nodes[aid] = CollabNode(agent_id=aid, playbook_id=pid, seguents=seg)
        if not nodes:
            raise AgentDefError(f"Col·laboració «{cid}» sense nodes")
        if len(nodes) > MAX_HANDOFFS:
            raise AgentDefError(f"Col·laboració «{cid}»: {len(nodes)} nodes > màxim {MAX_HANDOFFS}")
        inici = str(entry["inici"])
        if inici not in nodes:
            raise AgentDefError(f"Col·laboració «{cid}»: node inicial «{inici}» no definit")
        _detecta_cicle(nodes, inici)                  # SENSE cicles (INV-4)
        collabs[cid] = Collaboracio(id=cid, inici=inici, nodes=nodes)
    if not collabs:
        raise AgentDefError("Cap col·laboració definida")
    return collabs


@dataclass(frozen=True)
class PasCollaboracio:
    """Un pas resolt del graf: quin agent, amb quin playbook i en quina Session ÚNICA."""
    ordre: int
    agent_id: str
    role: str
    playbook_id: str
    session: Session


class Coordinador:
    """Recorre un graf de col·laboració signat i produeix l'ORDRE d'execució amb una
    Session ÚNICA per node (anti confused-deputy). NO executa: cada pas es delega
    després a Orchestrator.run (RBAC per agent + ApprovalGate), com qualsevol Plan."""

    def __init__(self, registry: SignedAgentRegistry) -> None:
        self._registry = registry

    def pla_execucio(self, collab: Collaboracio, *, tenant_id: str, base_session_id: str,
                     timeout_s: float = 120.0, max_steps: int = 10) -> list[PasCollaboracio]:
        ordre: list[PasCollaboracio] = []
        vistos: set[str] = set()
        ids_sessio: set[str] = set()

        def recorre(agent_id: str) -> None:
            if agent_id in vistos:
                return
            vistos.add(agent_id)
            node = collab.nodes[agent_id]
            agent = self._registry.require(agent_id)        # INV-4: agent del registre signat
            sid = f"{base_session_id}:{len(ordre)}:{agent_id}"  # ÚNIC i no reutilitzat
            if sid in ids_sessio:  # defensa extra (no hauria de passar mai)
                raise AgentDefError(f"session_id duplicat «{sid}» — anti confused-deputy")
            ids_sessio.add(sid)
            ctx = ImmutableContext(session_id=sid, tenant_id=tenant_id, role=agent.role, data={})
            sess = Session(ctx, Budget(max_steps=max_steps), Deadline(timeout_s))
            ordre.append(PasCollaboracio(ordre=len(ordre), agent_id=agent_id, role=agent.role,
                                          playbook_id=node.playbook_id, session=sess))
            for seg in node.seguents:
                recorre(seg)

        recorre(collab.inici)
        return ordre


# ── K13.3 · Canal entre agents: missatges com a DADES NO executables ─────────
def embolcalla_missatge_agent(text: str) -> str:
    """Embolcalla un missatge entre agents com a DADA no fiable (<DATA>, anti-breakout)."""
    return wrap_untrusted(text)


def missatge_es_injeccio(text: str) -> bool:
    """Cert si el missatge entre agents sembla un intent d'injecció (s'ha d'escalar,
    mai executar com a instrucció)."""
    return detect_injection(text).is_injection
