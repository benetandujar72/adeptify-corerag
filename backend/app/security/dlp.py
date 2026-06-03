"""Detecció DLP (Data Loss Prevention) per regex.

Pre-screening barat per a auditories diàries. Per a una detecció més fina
recomanem **Microsoft Presidio** com a layer addicional (la integració és
opcional i s'invoca si la llibreria està disponible).

Patrons coberts:
- DNI / NIE (Espanya).
- E-mail.
- Telèfon ES (mòbil/fix).
- IBAN ES (24 caràcters).
- Paraules clau confidencials (notes, expedient, contrasenya, etc.).

Cada detecció retorna un `Coincidencia` amb el tipus, el fragment redactat
(sense exposar el valor sencer als logs) i la posició.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# ─────────────────────────── Patrons ───────────────────────────

_RE_DNI = re.compile(r"\b\d{8}[A-HJ-NP-TV-Z]\b")
_RE_NIE = re.compile(r"\b[XYZ]\d{7}[A-HJ-NP-TV-Z]\b")
_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_RE_TELEFON_ES = re.compile(r"(?:(?<!\d)(?:\+?34[\s-]?)?[6789]\d{2}[\s-]?\d{3}[\s-]?\d{3}(?!\d))")
_RE_IBAN_ES = re.compile(r"\bES\d{2}[\s-]?(?:\d{4}[\s-]?){5}\b")

# Paraules clau confidencials (insensible a majúscules).
_PARAULES_CONF = (
    "notes de l'alumne", "nota mitjana", "qualificació",
    "expedient acadèmic", "expedient disciplinari",
    "contrasenya", "password", "token", "api key",
    "informe psicopedagògic", "informe mèdic", "diagnòstic",
    "dni de", "telèfon de", "adreça de",
    "consentiment parental",
)
_RE_PARAULES = re.compile("|".join(re.escape(p) for p in _PARAULES_CONF), re.IGNORECASE)


@dataclass(frozen=True)
class Coincidencia:
    tipus: str         # "dni" | "nie" | "email" | "telefon" | "iban" | "paraula_clau"
    fragment_redactat: str  # màscara segura per a logs (mai exposem el valor)
    inici: int
    fi: int


def _redacta(valor: str) -> str:
    """Manté els 2 primers i 2 últims caràcters; la resta amb asteriscs."""
    n = len(valor)
    if n <= 4:
        return "*" * n
    return f"{valor[:2]}{'*' * (n - 4)}{valor[-2:]}"


def escaneja(text: str) -> list[Coincidencia]:
    """Retorna totes les coincidències trobades a un text. No exposa valors."""
    if not text:
        return []
    out: list[Coincidencia] = []
    parelles = (
        ("dni", _RE_DNI),
        ("nie", _RE_NIE),
        ("email", _RE_EMAIL),
        ("telefon", _RE_TELEFON_ES),
        ("iban", _RE_IBAN_ES),
    )
    for tipus, regex in parelles:
        for m in regex.finditer(text):
            out.append(Coincidencia(
                tipus=tipus,
                fragment_redactat=_redacta(m.group(0).strip()),
                inici=m.start(), fi=m.end(),
            ))
    for m in _RE_PARAULES.finditer(text):
        out.append(Coincidencia(
            tipus="paraula_clau",
            fragment_redactat=m.group(0)[:24],  # paraula clau, no PII
            inici=m.start(), fi=m.end(),
        ))
    return out


def escaneja_textos(textos: Iterable[str]) -> list[Coincidencia]:
    """Agregat: aplica `escaneja` a una iterable de textos."""
    res: list[Coincidencia] = []
    for t in textos:
        res.extend(escaneja(t or ""))
    return res


def resum_severitat(coinc: list[Coincidencia]) -> str:
    """Severitat agregada: 'critica' si hi ha PII real; 'alta' si paraula clau; 'ok' si res."""
    tipus = {c.tipus for c in coinc}
    if tipus & {"dni", "nie", "iban"}:
        return "critica"
    if tipus & {"email", "telefon"}:
        return "alta"
    if "paraula_clau" in tipus:
        return "mitjana"
    return "ok"
