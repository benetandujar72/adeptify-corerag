"""Reranker bge-reranker-v2-m3 auto-allotjat, càrrega mandrosa.

Reordena els chunks recuperats segons la rellevància respecte de la pregunta i
en reté els top-N. En tests s'injecta un doble amb `set_reranker()`.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings


@dataclass
class CandidatRerank:
    """Parella (text, càrrega útil) a reordenar."""

    text: str
    payload: dict


class Reranker(Protocol):
    """Interfície d'un reranker."""

    def rerank(
        self, query: str, candidats: list[CandidatRerank], top_n: int
    ) -> list[tuple[CandidatRerank, float]]: ...


class BGEReranker:
    """Reranker real `BAAI/bge-reranker-v2-m3` via FlagEmbedding (mandrós)."""

    def __init__(self) -> None:
        self._model = None
        self._settings = get_settings()
        # El tokenizer ràpid (Rust) de FlagEmbedding NO és segur per a accés
        # concurrent: dues crides simultànies (FastAPI executa els handlers sync en
        # un threadpool) muten l'estat de truncation/padding i llancen
        # "RuntimeError: Already borrowed". Serialitzem amb un lock.
        self._lock = threading.Lock()

    def _carrega(self):
        if self._model is None:
            from FlagEmbedding import FlagReranker

            from app.rag.device import resol_device

            device = resol_device(self._settings.reranker_device)
            self._model = FlagReranker(
                self._settings.reranker_model,
                use_fp16=device != "cpu",
                devices=device,
            )
        return self._model

    def rerank(
        self, query: str, candidats: list[CandidatRerank], top_n: int
    ) -> list[tuple[CandidatRerank, float]]:
        if not candidats:
            return []
        parelles = [[query, c.text] for c in candidats]
        with self._lock:  # serialitza l'accés al tokenizer (evita "Already borrowed")
            model = self._carrega()
            scores = model.compute_score(parelles, normalize=True)
        if not isinstance(scores, list):
            scores = [scores]
        puntuats = sorted(
            zip(candidats, (float(s) for s in scores)),
            key=lambda x: x[1],
            reverse=True,
        )
        return puntuats[:top_n]


_reranker: Reranker | None = None


def get_reranker() -> Reranker:
    """Retorna el reranker actiu (mandrós)."""
    global _reranker
    if _reranker is None:
        _reranker = BGEReranker()
    return _reranker


def set_reranker(reranker: Reranker | None) -> None:
    """Injecta (o reinicia) el reranker. Pensat per a tests."""
    global _reranker
    _reranker = reranker
