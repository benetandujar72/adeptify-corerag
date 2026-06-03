"""Factory del magatzem vectorial. Llegeix la variable d'entorn `VECTOR_STORE`.

Valors:
- `pgvector` (per defecte): manté la implementació actual sobre PostgreSQL.
- `qdrant`: usa el client Qdrant (requereix QDRANT_URL i el SDK).

S'evita un singleton global per facilitar les proves (cada Settings pot
crear-ne una nova si cal); en producció el cost és menyspreable.
"""

from __future__ import annotations

import os
import threading

from app.rag.vectorstore.base import VectorStore

_lock = threading.Lock()
_instance: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """Retorna el magatzem actiu segons `VECTOR_STORE` (cache de procés)."""
    global _instance
    if _instance is not None:
        return _instance
    with _lock:
        if _instance is not None:
            return _instance
        nom = (os.environ.get("VECTOR_STORE") or "pgvector").strip().lower()
        if nom == "qdrant":
            from app.rag.vectorstore.qdrant_store import QdrantStore
            from app.core.config import get_settings

            _instance = QdrantStore(dim=get_settings().embedding_dim)
        else:
            from app.rag.vectorstore.pgvector_store import PgvectorStore

            _instance = PgvectorStore()
    return _instance


def _reinicialitza_per_test() -> None:
    """Permet als tests forçar un nou backend (no s'usa en prod)."""
    global _instance
    with _lock:
        _instance = None
