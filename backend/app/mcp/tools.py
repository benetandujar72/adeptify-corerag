"""Tools MCP del MVP (mockup 02).

Cada tool està estructurada com una tool MCP real (nom, esquema, executor) però
al MVP llegeix de la base de dades (chunks indexats) o de `sample_data`. Així,
quan es connectin orígens reals (Drive, Clickedu, Calendari de Google…), només
cal substituir l'executor mantenint el contracte.

Tools disponibles:
- drive            · cerca a documents compartits del centre
- materials        · cerca a apunts/exercicis docents
- base_nofc_pec    · cerca a la normativa (NOFC) i el projecte (PEC)
- calendari        · consulta el calendari escolar (sortides, períodes, festius)
- clickedu         · (placeholder) consulta a la plataforma de gestió
- cerca_web_local  · cerca acotada a dominis aprovats (placeholder offline)

Com afegir-ne una de nova: vegeu `app/mcp/README` dins el codi del servidor
(`server.registra`). N'hi ha prou amb crear un `MCPTool` i registrar-lo.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document
from app.mcp.types import MCPTool, MCPToolResult


# ───────────────────────── Cerca documental genèrica ────────────────────────


def _cerca_documents(
    db: Session, consulta: str, tipus: list[str] | None = None, limit: int = 5,
    institucio_id: str | None = None,
) -> MCPToolResult:
    """Cerca textual senzilla (ILIKE) sobre els chunks indexats.

    És deliberadament simple (no vectorial) perquè les tools MCP representen
    fonts «externes» consultables; el RAG vectorial real el fa el retriever.

    Si s'indica `institucio_id`, la cerca s'acota als documents d'aquesta
    institució (aïllament multi-tenant; defensa en profunditat per a quan
    aquestes tools s'invoquin amb context d'usuari).
    """
    stmt = (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.contingut.ilike(f"%{consulta}%"))
    )
    if institucio_id is not None:
        stmt = stmt.where(Document.institucio_id == institucio_id)
    if tipus:
        stmt = stmt.where(Document.tipus.in_(tipus))
    stmt = stmt.limit(limit)

    files = db.execute(stmt).all()
    resultats = []
    fonts = []
    for chunk, document in files:
        resultats.append(
            {
                "filename": document.filename,
                "pagina": chunk.pagina,
                "fragment": chunk.contingut[:400],
            }
        )
        fonts.append(
            {
                "doc_id": document.doc_id,
                "filename": document.filename,
                "tipus": document.tipus,
                "pagina": chunk.pagina,
            }
        )
    return MCPToolResult(ok=True, contingut=resultats, fonts=fonts)


_SCHEMA_CONSULTA = {
    "type": "object",
    "properties": {
        "consulta": {"type": "string", "description": "Text a cercar."},
        "limit": {"type": "integer", "default": 5},
    },
    "required": ["consulta"],
}


def construeix_tools(db: Session, institucio_id: str | None = None) -> dict[str, MCPTool]:
    """Construeix les tools MCP lligades a una sessió de BD concreta.

    Si s'indica `institucio_id`, totes les cerques documentals queden acotades a
    aquesta institució (aïllament multi-tenant).
    """

    def drive(consulta: str, limit: int = 5) -> MCPToolResult:
        return _cerca_documents(db, consulta, limit=limit, institucio_id=institucio_id)

    def materials(consulta: str, limit: int = 5) -> MCPToolResult:
        # Materials docents: prioritzem documents tipus md/docx/pdf.
        return _cerca_documents(db, consulta, limit=limit, institucio_id=institucio_id)

    def base_nofc_pec(consulta: str, limit: int = 5) -> MCPToolResult:
        return _cerca_documents(db, consulta, limit=limit, institucio_id=institucio_id)

    def calendari(consulta: str, limit: int = 5) -> MCPToolResult:
        # El calendari escolar viu com a document a sample_data; el cerquem.
        termes = f"{consulta} calendari sortida període festiu".strip()
        return _cerca_documents(db, termes, limit=limit, institucio_id=institucio_id)

    def clickedu(consulta: str, limit: int = 5) -> MCPToolResult:
        # Placeholder: al MVP no hi ha connexió viva amb Clickedu.
        return MCPToolResult(
            ok=True,
            contingut={
                "nota": (
                    "Connector Clickedu no disponible al MVP. "
                    "S'activarà amb SSO/API de la plataforma."
                ),
                "consulta": consulta,
            },
        )

    def cerca_web_local(consulta: str, limit: int = 5) -> MCPToolResult:
        # Placeholder offline: només dominis aprovats; sense egress al MVP.
        return MCPToolResult(
            ok=True,
            contingut={
                "nota": (
                    "Cerca web local restringida a dominis aprovats. "
                    "Desactivada al MVP per garantir crides_externes=0."
                ),
                "consulta": consulta,
                "dominis_aprovats": ["xtec.cat", "gencat.cat"],
            },
        )

    definicions: list[tuple[str, str, Any]] = [
        ("drive", "Cerca a documents compartits del Drive del centre.", drive),
        ("materials", "Cerca a apunts i exercicis del repositori docent.", materials),
        ("base_nofc_pec", "Cerca a la normativa NOFC i al projecte PEC.", base_nofc_pec),
        ("calendari", "Consulta el calendari escolar: sortides, períodes i festius.", calendari),
        ("clickedu", "Consulta la plataforma de gestió Clickedu (placeholder).", clickedu),
        (
            "cerca_web_local",
            "Cerca web acotada a dominis aprovats (desactivada al MVP).",
            cerca_web_local,
        ),
    ]

    tools: dict[str, MCPTool] = {}
    for nom, descripcio, executor in definicions:
        tools[nom] = MCPTool(
            nom=nom,
            descripcio=descripcio,
            input_schema=_SCHEMA_CONSULTA,
            executor=executor,
        )
    return tools
