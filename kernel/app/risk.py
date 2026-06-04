"""K2.3 — Taxonomia de risc per eina.

Nivells ORDINALS (com més alt, més perillós). La política (K2.1) i el kernel
d'eines (INV-2) decideixen segons aquest nivell i el rol.
"""

from __future__ import annotations

from enum import IntEnum


class RiskLevel(IntEnum):
    """Risc d'una eina (taxonomia fixa del backlog)."""

    INFO = 0           # només informació, sense efectes
    READ = 1           # lectura de dades
    WRITE_LOCAL = 2    # escriptura local (BD/FS del centre)
    WRITE_EXTERNAL = 3 # escriptura cap a un sistema extern
    IRREVERSIBLE = 4   # acció irreversible (esborrats massius, pagaments...)

    @property
    def etiqueta(self) -> str:
        return {
            0: "info", 1: "read", 2: "write-local",
            3: "write-external", 4: "irreversible",
        }[int(self)]


def parse_risk(valor: int | str | RiskLevel) -> RiskLevel:
    """Converteix un enter/etiqueta/enum a RiskLevel (per llegir l'allowlist)."""
    if isinstance(valor, RiskLevel):
        return valor
    if isinstance(valor, int):
        return RiskLevel(valor)
    text = str(valor).strip().lower().replace("_", "-")
    per_etiqueta = {r.etiqueta: r for r in RiskLevel}
    if text in per_etiqueta:
        return per_etiqueta[text]
    if text.isdigit():
        return RiskLevel(int(text))
    raise ValueError(f"Nivell de risc desconegut: {valor!r}")
