"""K3.3 — Pin/firma SHA-256 de servidors MCP locals.

Cada servidor MCP local té un PIN (sha256 del seu descriptor/manifest). En connectar,
es recalcula el hash del descriptor i es rebutja si: (a) el servidor no és a la llista
de pins coneguts, o (b) el hash no coincideix (descriptor modificat). Sense pin
conegut → rebuig (no hi ha descobriment dinàmic de servidors).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .errors import McpPinError


def descriptor_hash(descriptor: bytes | str) -> str:
    if isinstance(descriptor, str):
        descriptor = descriptor.encode("utf-8")
    return hashlib.sha256(descriptor).hexdigest()


@dataclass(frozen=True)
class McpPin:
    name: str
    sha256: str


class McpPinRegistry:
    """Llista estàtica de pins coneguts (font de confiança, fora del runtime)."""

    def __init__(self, pins: dict[str, str] | None = None) -> None:
        self._pins = dict(pins or {})

    def add(self, name: str, sha256: str) -> None:
        self._pins[name] = sha256

    @property
    def names(self) -> set[str]:
        return set(self._pins)

    def verify(self, name: str, descriptor: bytes | str) -> McpPin:
        """Retorna el pin si coincideix; llança McpPinError si falta o no quadra."""
        esperat = self._pins.get(name)
        if esperat is None:
            raise McpPinError(f"Servidor MCP «{name}» sense pin conegut (rebutjat)")
        actual = descriptor_hash(descriptor)
        if actual != esperat:
            raise McpPinError(
                f"Pin del servidor MCP «{name}» no coincideix "
                f"(esperat {esperat[:12]}…, és {actual[:12]}…)"
            )
        return McpPin(name=name, sha256=esperat)
