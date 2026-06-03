"""Suggeriment de recursos de documentació per tema (F2, docs/20).

Donada una consulta, retorna els recursos CURATS de la institució que hi encaixen
(per solapament de paraules clau amb les etiquetes i el títol). MAI genera enllaços:
només selecciona del registre verificat (`recursos_documentacio`). Respecta institució,
vigència i, per als de tipus "document", la visibilitat segons el rol.
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import RecursSuggerit
from app.core.roles import Rol
from app.db.models import Document

try:  # CORE: el registre de recursos curats (RecursDocumentacio) viu a la SUITE.
    from app.db.models_domini import RecursDocumentacio
except Exception:  # noqa: BLE001 - sense mòdul de domini, el core no suggereix recursos
    RecursDocumentacio = None  # type: ignore[assignment]

_ROLS_ADMIN_DOC = {Rol.DIRECCIO, Rol.PAS, Rol.SUPERADMIN}

# Paraules massa genèriques per encaixar temes (no aporten senyal).
_ATURADES = frozenset({
    "amb", "per", "una", "uns", "les", "els", "del", "dels", "que", "com", "sobre",
    "quin", "quina", "quins", "quines", "cal", "documentacio", "documentació",
    "necessaris", "necessari", "aquest", "aquesta", "tinc", "vull", "fer",
})


def _tokens(text: str) -> set[str]:
    """Tokens normalitzats (minúscules, sense accents, ≥4 lletres, sense aturades)."""
    t = unicodedata.normalize("NFKD", (text or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return {m for m in re.findall(r"[a-z0-9]+", t) if len(m) >= 4 and m not in _ATURADES}


def suggereix_recursos(
    db: Session, institucio: str, text: str, rol: Rol, limit: int = 4
) -> list[RecursSuggerit]:
    """Recursos verificats que encaixen amb la consulta (top-N per solapament)."""
    if RecursDocumentacio is None:  # CORE sense registre de recursos de domini
        return []
    try:
        files = db.scalars(
            select(RecursDocumentacio).where(
                RecursDocumentacio.institucio_id == institucio,
                RecursDocumentacio.vigent.is_(True),
            )
        ).all()
    except Exception:  # noqa: BLE001 - si la taula no hi és o falla, no suggerim res
        return []
    tokens_consulta = _tokens(text)
    if not files or not tokens_consulta:
        return []

    es_admin = rol in _ROLS_ADMIN_DOC
    puntuats: list[tuple[int, RecursDocumentacio]] = []
    for r in files:
        tags: set[str] = set()
        for e in r.etiquetes or []:
            tags |= _tokens(str(e))
        tags |= _tokens(r.titol or "")
        overlap = len(tokens_consulta & tags)
        if overlap == 0:
            continue
        # Recurs de tipus "document": respecta l'aïllament i la visibilitat.
        if r.tipus == "document" and r.doc_id:
            doc = db.scalar(
                select(Document).where(
                    Document.doc_id == r.doc_id, Document.institucio_id == institucio
                )
            )
            if doc is None or (doc.visibilitat == "admin" and not es_admin):
                continue
        puntuats.append((overlap, r))

    puntuats.sort(key=lambda x: x[0], reverse=True)
    return [
        RecursSuggerit(
            id=r.id, titol=r.titol, descripcio=r.descripcio or "", tipus=r.tipus,
            url=r.url, doc_id=r.doc_id, versio=r.versio or "", font_oficial=r.font_oficial or "",
        )
        for _, r in puntuats[:limit]
    ]
