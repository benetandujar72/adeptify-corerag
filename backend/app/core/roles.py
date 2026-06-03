"""Rols del sistema (RBAC).

Els quatre rols del contracte (API_CONTRACT.md §Rols): docent, alumne, familia,
direccio. Es defineixen com a `Enum` de cadena per validar tokens i filtrar
agents i documents.
"""

from __future__ import annotations

from enum import Enum


class Rol(str, Enum):
    """Rols d'usuari reconeguts pel sistema."""

    DOCENT = "docent"
    ALUMNE = "alumne"
    FAMILIA = "familia"
    DIRECCIO = "direccio"
    PAS = "pas"  # Personal d'Administració i Serveis
    SUPERADMIN = "superadmin"  # Gestió total de la plataforma


ROLS_VALIDS: frozenset[str] = frozenset(r.value for r in Rol)


def es_rol_valid(valor: str) -> bool:
    """Indica si una cadena correspon a un rol reconegut."""
    return valor in ROLS_VALIDS
