"""Dobles deterministes de LLM, embeddings i reranker (sense GPU ni xarxa).

Aquests dobles s'usen en DOS llocs, sense duplicar-los:

- `tests/conftest.py` els injecta als singletons abans de cada test.
- `eval/run_eval.py --mock` els injecta per córrer l'avaluació a la CI sense GPU.

Cap d'ells descarrega models de HuggingFace ni fa cap crida de xarxa: les
respostes i puntuacions són deterministes i derivades del text d'entrada.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


class FakeEmbedder:
    """Embedder fals: vectors deterministes derivats del text (sense models)."""

    def __init__(self, dim: int = 8) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def _vec(self, text: str) -> list[float]:
        base = [0.0] * self._dim
        for i, ch in enumerate(text):
            base[i % self._dim] += (ord(ch) % 17) / 17.0
        norma = sum(v * v for v in base) ** 0.5 or 1.0
        return [v / norma for v in base]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


class FakeReranker:
    """Reranker fals: ordena per solapament de paraules amb la pregunta."""

    def rerank(self, query: str, candidats, top_n: int):
        termes = set(query.lower().split())
        puntuats = []
        for c in candidats:
            paraules = set(c.text.lower().split())
            inter = len(termes & paraules)
            score = inter / (len(termes) or 1)
            puntuats.append((c, min(1.0, 0.5 + score)))
        puntuats.sort(key=lambda x: x[1], reverse=True)
        return puntuats[:top_n]


class FakeLLM:
    """Client LLM fals: respostes deterministes, sense cap crida de xarxa.

    Per defecte respon un text fix (com als tests). Per a l'avaluació offline és
    útil que la resposta reflecteixi el context recuperat, de manera que les
    comprovacions de `contains` siguin significatives: amb `eco_context=True`,
    concatena el contingut dels blocs de CONTEXT del prompt a la resposta.
    """

    def __init__(self, eco_context: bool = False) -> None:
        self.ultim_prompt: list[dict[str, str]] | None = None
        self._eco_context = eco_context

    def _resposta(self, messages: list[dict[str, str]]) -> str:
        base = "Resposta de prova basada en el context. Font [1]."
        if not self._eco_context:
            return base
        # Recupera el bloc de CONTEXT del darrer missatge d'usuari i el reflecteix
        # perquè les comprovacions de groundedness/contains tinguin sentit offline.
        context = ""
        for msg in messages:
            if msg.get("role") == "user" and "CONTEXT" in msg.get("content", ""):
                context = msg["content"]
        return f"{base}\n{context}"

    def complete(self, messages, **kwargs) -> str:
        self.ultim_prompt = messages
        return self._resposta(messages)

    def stream(self, messages, **kwargs) -> Iterator[str]:
        self.ultim_prompt = messages
        for token in ["Resposta ", "de ", "prova ", "[1]."]:
            yield token
