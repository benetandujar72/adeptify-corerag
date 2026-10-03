"""Embeddings bge-m3 auto-allotjats, carregats de forma mandrosa.

El model (`BAAI/bge-m3`, 1024 dim) es carrega via FlagEmbedding NOMÉS la primera
vegada que es demana un embedding. En tests s'injecta un doble amb
`set_embedder()` perquè no calgui descarregar res de HuggingFace.
"""

from __future__ import annotations

import threading
from typing import Protocol

from app.core.config import get_settings


class Embedder(Protocol):
    """Interfície d'un generador d'embeddings."""

    @property
    def dim(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class BGEEmbedder:
    """Embedder real sobre `BAAI/bge-m3` via FlagEmbedding (càrrega mandrosa)."""

    def __init__(self) -> None:
        self._model = None
        self._settings = get_settings()
        # El tokenizer ràpid no és segur per a accés concurrent (vegeu rerank.py):
        # serialitzem `encode` per evitar "RuntimeError: Already borrowed".
        self._lock = threading.Lock()

    def _carrega(self):
        if self._model is None:
            # Importació diferida: només quan realment cal inferir.
            from FlagEmbedding import BGEM3FlagModel

            from app.rag.device import resol_device

            device = resol_device(self._settings.embedder_device)
            self._model = BGEM3FlagModel(
                self._settings.embedding_model,
                use_fp16=device != "cpu",
                devices=device,
                trust_remote_code=False,
            )
        return self._model

    @property
    def dim(self) -> int:
        return self._settings.embedding_dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        with self._lock:  # serialitza l'accés al tokenizer (evita "Already borrowed")
            model = self._carrega()
            sortida = model.encode(texts, return_dense=True)["dense_vecs"]
        return [list(map(float, vec)) for vec in sortida]

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    """Retorna l'embedder actiu (mandrós)."""
    global _embedder
    if _embedder is None:
        _embedder = BGEEmbedder()
    return _embedder


def set_embedder(embedder: Embedder | None) -> None:
    """Injecta (o reinicia) l'embedder. Pensat per a tests."""
    global _embedder
    _embedder = embedder
