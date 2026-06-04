"""K8.4 — Procedència anti-enverinament del RAG.

Cada fragment (chunk) té una procedència registrada: (source_id, sha256 del
contingut). En el retrieval, es recalcula el hash i es DESCARTA qualsevol chunk
que: (a) no tingui procedència registrada, o (b) tingui un hash que no coincideix
(contingut alterat). Així un chunk enverinat o sense origen mai entra al context.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


def chunk_hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChunkProvenance:
    chunk_id: str
    source_id: str
    sha256: str


class ProvenanceRegistry:
    """Registre de procedència per chunk (poblat en la ingesta, font de confiança)."""

    def __init__(self) -> None:
        self._by_id: dict[str, ChunkProvenance] = {}

    def register(self, *, chunk_id: str, source_id: str, content: str) -> ChunkProvenance:
        prov = ChunkProvenance(chunk_id=chunk_id, source_id=source_id, sha256=chunk_hash(content))
        self._by_id[chunk_id] = prov
        return prov

    def get(self, chunk_id: str) -> ChunkProvenance | None:
        return self._by_id.get(chunk_id)

    def is_valid(self, *, chunk_id: str, content: str) -> bool:
        prov = self._by_id.get(chunk_id)
        return prov is not None and prov.sha256 == chunk_hash(content)


def filter_valid_chunks(registry: ProvenanceRegistry, chunks: list[dict]) -> tuple[list[dict], list[dict]]:
    """Separa (vàlids, descartats). `chunks` = [{id, content, ...}].

    Es descarta tot chunk sense procedència o amb hash alterat (K8.4)."""
    kept: list[dict] = []
    dropped: list[dict] = []
    for c in chunks:
        cid = c.get("id", "")
        if registry.is_valid(chunk_id=cid, content=c.get("content", "")):
            kept.append(c)
        else:
            dropped.append(c)
    return kept, dropped
