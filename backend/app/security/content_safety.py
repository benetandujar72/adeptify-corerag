"""Classificació de seguretat per contingut didàctic i sortida a IA externa.

Objectiu: permetre reutilitzar materials de Moodle/Classroom/Drive per generar
contingut sense exposar dades personals de menors, avaluacions o informació
educativa sensible a proveïdors externs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Literal

from app.security import dlp

Sensibilitat = Literal["public", "docent", "intern", "sensible"]

_PATRONS_MENORS = re.compile(
    r"\b("
    r"alumne|alumna|alumnat|menor|fam[ií]lia|mare|pare|tutor|tutora|"
    r"nee|nese|neae|dua individual|pla individualitzat|pi\b|"
    r"tdah|tea|disl[eè]xia|diagn[oò]stic|psicopedag[oò]gic|"
    r"salut|m[eè]dic|conducta|absentisme|expedient|"
    r"asma|diabetis|epil[eè]psia|al[·.]?l[eè]rgia|alergia|medicaci[oó]|"
    r"cel[ií]ac|cel[ií]aca|celiaquia|anafilaxi|discapacitat|malaltia|"
    r"nota|notes|qualificaci[oó]|avaluaci[oó] individual|"
    r"entrega|lliurament|feedback individual|butllet[ií]"
    r")\b",
    re.IGNORECASE,
)

_PATRONS_DOCENTS_OK = re.compile(
    r"\b("
    r"situaci[oó] d.aprenentatge|sda|unitat|sessio|sessi[oó]|"
    r"exercici|q[uü]estionari|rubrica|r[uú]brica|compet[eè]ncia|criteri|"
    r"sabers|objectius|activitat|material|recurs|programaci[oó]"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClassificacioContingut:
    sensibilitat: Sensibilitat
    exportable_ia: bool
    severitat_dlp: str
    motius: list[str] = field(default_factory=list)
    deteccions: dict[str, int] = field(default_factory=dict)


def _agrega_deteccions(coinc: Iterable[dlp.Coincidencia]) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in coinc:
        out[c.tipus] = out.get(c.tipus, 0) + 1
    return out


def classifica_text(text: str, *, origen: str = "manual") -> ClassificacioContingut:
    """Classifica un text per al RAG i per a possible ús amb IA externa.

    Regla conservadora: qualsevol PII real o paraula educativa sensible bloqueja
    la sortida externa. El text pot seguir entrant al RAG intern/local amb
    etiqueta `sensible`, sempre que RBAC i auditoria ho permetin.
    """

    contingut = text or ""
    coincidencies = dlp.escaneja(contingut)
    severitat = dlp.resum_severitat(coincidencies)
    deteccions = _agrega_deteccions(coincidencies)
    motius: list[str] = []

    if severitat != "ok":
        motius.append(f"dlp_{severitat}")

    if _PATRONS_MENORS.search(contingut):
        motius.append("educacio_menors_o_avaluacio")

    if severitat in {"critica", "alta"} or "educacio_menors_o_avaluacio" in motius:
        return ClassificacioContingut(
            sensibilitat="sensible",
            exportable_ia=False,
            severitat_dlp=severitat,
            motius=motius,
            deteccions=deteccions,
        )

    if severitat == "mitjana":
        return ClassificacioContingut(
            sensibilitat="intern",
            exportable_ia=False,
            severitat_dlp=severitat,
            motius=motius,
            deteccions=deteccions,
        )

    if origen in {"curriculum", "public_curriculum"}:
        sensibilitat: Sensibilitat = "public"
    elif origen in {"moodle", "classroom", "drive", "manual"} and _PATRONS_DOCENTS_OK.search(contingut):
        sensibilitat = "docent"
    else:
        sensibilitat = "intern"

    return ClassificacioContingut(
        sensibilitat=sensibilitat,
        exportable_ia=sensibilitat in {"public", "docent"},
        severitat_dlp=severitat,
        motius=motius,
        deteccions=deteccions,
    )


def classifica_textos(textos: Iterable[str], *, origen: str = "manual") -> ClassificacioContingut:
    """Classifica un conjunt de fragments amb la màxima severitat detectada."""

    combinat = "\n\n".join(t or "" for t in textos)
    return classifica_text(combinat, origen=origen)


def exigeix_sortida_externa_permesa(text: str) -> ClassificacioContingut:
    """Fail-closed abans d'enviar res a un LLM extern."""

    c = classifica_text(text, origen="external_prompt")
    if not c.exportable_ia:
        raise ValueError(
            "El contingut no pot sortir a IA externa: "
            + (", ".join(c.motius) if c.motius else c.sensibilitat)
        )
    return c
