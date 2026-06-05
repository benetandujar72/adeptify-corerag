"""K10 (F4) — Playbooks declaratius signats GPG → materialització a Plan.

Un PLAYBOOK és una seqüència de passos PRE-APROVADA i SIGNADA (mateix patró que
l'allowlist d'eines, K3.1): defineix uns paràmetres tipats i uns passos que només
referencien eines de l'allowlist. NO és una nova via d'execució — `instantiate()`
produeix el MATEIX `Plan` finit que ja consumeix `Orchestrator.run()`, que segueix
passant per RBAC (INV-2) → ApprovalGate (K6) → schema (K3.2) → callable pre-registrat
(INV-1). El que canvia és D'ON ve el Plan (una plantilla signada), mai què en fa el kernel.

Contracte F4↔F5 (el que F5 consumirà): `SignedPlaybookCatalog` (id → Playbook amb
esquema de params, risc_max, descripció) + `instantiate(playbook, params) → Plan`.

Garanties (fail-closed):
- Càrrega NOMÉS després de verificar la signatura GPG amb pinning de fingerprint (G-D).
- Cada `tool_id` d'un pas ∈ allowlist signada; risc de l'eina ≤ `risc_max` del playbook.
- Substitució de paràmetres NOMÉS per IGUALTAT EXACTA de clau `{param:NOM}` (mai
  concatenació/f-string/eval sobre input → INV-1). Plantilles amb `{param:` parcial es rebutgen.
- Validació estricta de params (tipus, requerits, sense desconeguts) a `instantiate()`.
- Guarda anti-PII (G-I): es rebutgen valors fixos/params amb PII evident (DNI/NIE/email/telèfon).
  NOTA: és una barrera grossera per patró; la frontera semàntica de PII de menors viu al SUITE.
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field

import strictyaml

from .allowlist import SignedAllowlist, fingerprint_de_confianca, verify_gpg_signature
from .errors import PlaybookError
from .orchestrator import Plan, PlanStep
from .risk import RiskLevel, parse_risk

# Límit dur de passos d'un Plan materialitzat (coherent amb K1.2; defensa anti-explosió).
MAX_PASSOS_PLAYBOOK = 25

_TIPUS = {"str": str, "int": int, "float": float, "bool": bool}
_PLACEHOLDER_EXACTE = re.compile(r"^\{param:([A-Za-z_][A-Za-z0-9_]*)\}$")
_PLACEHOLDER_QUALSEVOL = re.compile(r"\{param:")

# Guarda anti-PII evident (barrera grossera al CORE; el SUITE té la frontera semàntica).
_RE_PII = re.compile(
    r"\b\d{8}[A-Za-z]\b"                       # DNI
    r"|\b[XYZ]\d{7}[A-Za-z]\b"                 # NIE
    r"|\b[\w.+-]+@[\w-]+\.[\w.-]+\b"           # email
    r"|\b\d{9}\b",                             # telèfon (9 dígits)
    re.IGNORECASE,
)


def _conte_pii_evident(valor: object) -> bool:
    return isinstance(valor, str) and bool(_RE_PII.search(valor))


@dataclass(frozen=True)
class PlaybookParam:
    nom: str
    tipus: str            # "str" | "int" | "float" | "bool"
    requerit: bool = True
    defecte: object = None


@dataclass(frozen=True)
class PlaybookStep:
    tool_id: str
    args: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Playbook:
    id: str
    descripcio: str
    params: tuple[PlaybookParam, ...]
    passos: tuple[PlaybookStep, ...]
    risc_max: RiskLevel

    def param(self, nom: str) -> PlaybookParam | None:
        return next((p for p in self.params if p.nom == nom), None)


class SignedPlaybookCatalog:
    """Catàleg immutable de playbooks signats (mirall de SignedAllowlist)."""

    def __init__(self, playbooks: dict[str, Playbook], *, fingerprint: str | None = None) -> None:
        self._pb = dict(playbooks)
        self.fingerprint = fingerprint

    def __contains__(self, pid: str) -> bool:
        return pid in self._pb

    def get(self, pid: str) -> Playbook | None:
        return self._pb.get(pid)

    def require(self, pid: str) -> Playbook:
        pb = self._pb.get(pid)
        if pb is None:
            raise PlaybookError(f"Playbook «{pid}» FORA del catàleg signat")
        return pb

    @property
    def ids(self) -> set[str]:
        return set(self._pb)


def _bool_de(valor: object) -> bool:
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in ("true", "1", "si", "sí", "yes")


def _parse_param(entry: dict) -> PlaybookParam:
    nom = str(entry["nom"])
    tipus = str(entry.get("tipus", "str"))
    if tipus not in _TIPUS:
        raise PlaybookError(f"Param «{nom}»: tipus no permès «{tipus}» (només {sorted(_TIPUS)})")
    return PlaybookParam(
        nom=nom, tipus=tipus,
        requerit=_bool_de(entry.get("requerit", "true")),
        defecte=entry.get("defecte"),
    )


def _valida_args_plantilla(pid: str, args: dict, noms_param: set[str]) -> None:
    """Cap concatenació amb placeholders; els placeholders exactes referencien params declarats."""
    for clau, valor in args.items():
        if isinstance(valor, (dict, list, tuple)):
            # Args NIATS no permesos: la guarda anti-PII i la validació de placeholders
            # només inspeccionen escalars; un nivell d'indirecció els evadiria (red-team F4).
            raise PlaybookError(f"Playbook «{pid}»: l'arg «{clau}» és niat (dict/list); no permès")
        if not isinstance(valor, str):
            continue
        m = _PLACEHOLDER_EXACTE.match(valor)
        if m:
            if m.group(1) not in noms_param:
                raise PlaybookError(
                    f"Playbook «{pid}»: l'arg «{clau}» referencia un param no declarat «{m.group(1)}»")
        elif _PLACEHOLDER_QUALSEVOL.search(valor):
            raise PlaybookError(
                f"Playbook «{pid}»: l'arg «{clau}» usa un placeholder PARCIAL «{valor}»; "
                "només es permet la igualtat exacta {param:NOM} (sense concatenació)")


def load_signed_playbooks(*, data_path: str, sig_path: str, pubkey_path: str,
                          allowlist: SignedAllowlist,
                          gnupghome: str | None = None, verify: bool = True,
                          expected_fingerprint: str | None = None) -> SignedPlaybookCatalog:
    """Carrega el catàleg de playbooks DESPRÉS de verificar-ne la signatura GPG (amb
    pinning de fingerprint) i de validar-lo de forma encreuada contra l'allowlist."""
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
        raise PlaybookError(f"Playbooks YAML invàlid: {exc}") from exc

    playbooks: dict[str, Playbook] = {}
    for entry in doc.get("playbooks", []) or []:
        pid = str(entry["id"])
        risc_max = parse_risk(entry.get("risc_max", "info"))
        params = tuple(_parse_param(p) for p in (entry.get("params", []) or []))
        noms = {p.nom for p in params}
        passos: list[PlaybookStep] = []
        for pas in entry.get("passos", []) or []:
            tid = str(pas["tool_id"])
            eina = allowlist.get(tid)
            if eina is None:
                raise PlaybookError(f"Playbook «{pid}»: pas amb eina «{tid}» FORA de l'allowlist signada")
            if eina.risk > risc_max:
                raise PlaybookError(
                    f"Playbook «{pid}»: l'eina «{tid}» (risc {eina.risk.etiqueta}) supera "
                    f"el risc_max del playbook ({risc_max.etiqueta})")
            args = dict(pas.get("args", {}) or {})
            _valida_args_plantilla(pid, args, noms)
            passos.append(PlaybookStep(tool_id=tid, args=args))
        if not passos:
            raise PlaybookError(f"Playbook «{pid}» sense passos")
        if len(passos) > MAX_PASSOS_PLAYBOOK:
            raise PlaybookError(f"Playbook «{pid}»: {len(passos)} passos > màxim {MAX_PASSOS_PLAYBOOK}")
        playbooks[pid] = Playbook(id=pid, descripcio=str(entry.get("descripcio", "")),
                                  params=params, passos=tuple(passos), risc_max=risc_max)
    if not playbooks:
        raise PlaybookError("Catàleg de playbooks buit o sense secció 'playbooks'")
    return SignedPlaybookCatalog(playbooks, fingerprint=fingerprint)


def _coerce(param: PlaybookParam, valor: object) -> object:
    """Valida/coerciona un valor al tipus declarat (fail-closed)."""
    tipus = _TIPUS[param.tipus]
    if param.tipus == "bool":
        return _bool_de(valor)
    if param.tipus == "str":
        return str(valor)
    try:
        return tipus(valor)  # int(...) / float(...)
    except (ValueError, TypeError) as exc:
        raise PlaybookError(f"Param «{param.nom}»: «{valor!r}» no és {param.tipus}") from exc


def instantiate(playbook: Playbook, params: dict | None = None) -> Plan:
    """Materialitza un Playbook + params en un Plan finit (K10.2). Determinista, sense
    `eval`/f-string sobre input: substitució NOMÉS per igualtat exacta {param:NOM}."""
    params = dict(params or {})
    noms = {p.nom for p in playbook.params}

    # Rebuig de params desconeguts (fail-closed: cap clau no declarada).
    desconeguts = set(params) - noms
    if desconeguts:
        raise PlaybookError(f"Playbook «{playbook.id}»: params desconeguts {sorted(desconeguts)}")

    # Resol valors finals dels params (requerits presents, tipus correctes, defectes).
    valors: dict[str, object] = {}
    for p in playbook.params:
        if p.nom in params:
            valors[p.nom] = _coerce(p, params[p.nom])
        elif p.requerit and p.defecte is None:
            raise PlaybookError(f"Playbook «{playbook.id}»: falta el param requerit «{p.nom}»")
        else:
            valors[p.nom] = _coerce(p, p.defecte) if p.defecte is not None else None
        if _conte_pii_evident(valors[p.nom]):
            raise PlaybookError(
                f"Playbook «{playbook.id}»: el param «{p.nom}» sembla contenir PII evident; "
                "el CORE no pot rebre PII (frontera transversal)")

    # Substitueix els placeholders exactes; els valors fixos es comproven anti-PII.
    steps: list[PlanStep] = []
    for pas in playbook.passos:
        args: dict = {}
        for clau, valor in pas.args.items():
            if isinstance(valor, (dict, list, tuple)):
                raise PlaybookError(f"Playbook «{playbook.id}»: arg «{clau}» niat no permès")
            if isinstance(valor, str):
                m = _PLACEHOLDER_EXACTE.match(valor)
                if m:
                    args[clau] = valors.get(m.group(1))
                    continue
                if _conte_pii_evident(valor):
                    raise PlaybookError(
                        f"Playbook «{playbook.id}»: arg fix «{clau}» amb PII evident")
            args[clau] = valor
        steps.append(PlanStep(tool_id=pas.tool_id, args=args))

    if len(steps) > MAX_PASSOS_PLAYBOOK:
        raise PlaybookError(f"Playbook «{playbook.id}»: {len(steps)} passos > màxim {MAX_PASSOS_PLAYBOOK}")
    return Plan(tuple(steps))
