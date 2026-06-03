"""Tipus base de la capa MCP: definició de tool i resultat.

Modelat segons el protocol MCP (Model Context Protocol): cada tool té un nom,
una descripció, un esquema d'entrada (JSON Schema) i una funció executora. El
resultat és sempre un objecte serialitzable amb el contingut i metadades.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPToolResult:
    """Resultat d'una invocació de tool MCP."""

    ok: bool
    contingut: Any
    # Fonts MCP (documents/recursos) que han contribuït al resultat.
    fonts: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


@dataclass
class MCPTool:
    """Definició d'una tool MCP."""

    nom: str
    descripcio: str
    input_schema: dict[str, Any]
    executor: Callable[..., MCPToolResult]

    def invoca(self, **kwargs: Any) -> MCPToolResult:
        try:
            return self.executor(**kwargs)
        except Exception as exc:  # noqa: BLE001 - encapsulem l'error a la tool
            return MCPToolResult(ok=False, contingut=None, error=str(exc))

    def descriptor(self) -> dict[str, Any]:
        """Descriptor serialitzable (estil MCP `tools/list`)."""
        return {
            "name": self.nom,
            "description": self.descripcio,
            "inputSchema": self.input_schema,
        }
