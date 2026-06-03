"""Servidor MCP intern.

Exposa el registre de tools (estil MCP `tools/list` + `tools/call`) i les fa
invocables des dels agents. Al MVP corre dins el procés del backend (no com a
procés MCP separat), però l'API imita el protocol perquè el salt a un servidor
MCP autònom sigui directe.

── Com afegir una tool nova ──────────────────────────────────────────────────
1. Defineix l'executor i el seu `input_schema` a `app/mcp/tools.py`.
2. Afegeix-lo a la llista `definicions` de `construeix_tools`.
3. Declara el nom de la tool al camp `tools` de l'agent corresponent
   (`app/agents/registry.py`). Cap altre canvi és necessari: l'orquestrador i
   l'API la descobreixen automàticament.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.mcp.tools import construeix_tools
from app.mcp.types import MCPTool, MCPToolResult


class MCPServer:
    """Registre i invocador de tools MCP per a una sessió de BD."""

    def __init__(self, db: Session, institucio_id: str | None = None) -> None:
        self._tools: dict[str, MCPTool] = construeix_tools(db, institucio_id=institucio_id)

    def registra(self, tool: MCPTool) -> None:
        """Registra (o substitueix) una tool al servidor."""
        self._tools[tool.nom] = tool

    def llista_tools(self, noms: list[str] | None = None) -> list[dict[str, Any]]:
        """Descriptors de tools (estil MCP `tools/list`).

        Si `noms` s'indica, només es retornen les tools disponibles per a aquest
        subconjunt (les tools permeses d'un agent).
        """
        items = self._tools.values()
        if noms is not None:
            items = [t for t in items if t.nom in set(noms)]
        return [t.descriptor() for t in items]

    def invoca(self, nom: str, **kwargs: Any) -> MCPToolResult:
        """Invoca una tool pel nom (estil MCP `tools/call`)."""
        tool = self._tools.get(nom)
        if tool is None:
            return MCPToolResult(
                ok=False, contingut=None, error=f"Tool MCP desconeguda: {nom}"
            )
        return tool.invoca(**kwargs)

    def noms(self) -> list[str]:
        return list(self._tools.keys())


def get_mcp_server(db: Session, institucio_id: str | None = None) -> MCPServer:
    """Construeix un servidor MCP lligat a la sessió de BD donada.

    `institucio_id` (opcional) acota les cerques documentals a una institució
    (aïllament multi-tenant).
    """
    return MCPServer(db, institucio_id=institucio_id)
