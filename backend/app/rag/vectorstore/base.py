"""Interfície base del magatzem vectorial (abstracció).

Tota la lògica RAG consulta aquesta interfície, no l'ORM ni el client Qdrant.
Així el codi de domini és INDEPENDENT del backend de vectors. Per canviar de
backend cal nomes una variable d'entorn (`VECTOR_STORE`).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Iterable

# Namespaces estàndard per a l'aïllament físic per canal/visibilitat.
# Mai es manipulen des del prompt: són filtres a la capa de dades.
NAMESPACE_PUBLIC = "publico"      # canal públic web (FAQ, info general)
NAMESPACE_INTERN = "intern"       # canal autenticat (documents del centre)


@dataclass(frozen=True)
class SearchFilter:
    """Filtre estructurat per a la cerca vectorial.

    Tots els camps són opcionals: el caller indica EXPLÍCITAMENT els filtres
    requerits per la política d'autorització. La capa de dades els aplica
    abans de retornar candidats; mai es delega l'autorització al model.

    - `namespaces`: namespaces autoritzats (qualsevol pot encaixar).
    - `institucio_id`: aïllament multi-tenant (single value).
    - `doc_ids`: limita a documents concrets (RBAC de fila / coneixement skill).
    - `excloure_visibilitat`: NO retornar documents amb aquestes visibilitats
      (típicament "admin" per a usuaris no admins).
    """

    namespaces: tuple[str, ...] | None = None
    institucio_id: str | None = None
    doc_ids: tuple[str, ...] | None = None
    excloure_visibilitat: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class VectorHit:
    """Resultat d'una cerca vectorial (chunk + metadades del document)."""

    chunk_id: str
    document_id: str
    doc_id: str
    filename: str
    tipus: str
    pagina: int | None
    verificat_el: str | None
    institucio_id: str
    namespace: str
    visibilitat: str
    contingut: str
    embedding: list[float] | None = None  # només present si el backend ho retorna
    score: float = 0.0


class VectorStore(abc.ABC):
    """Contracte que ha de complir tot magatzem vectorial integrat."""

    @abc.abstractmethod
    def search(
        self,
        vector: list[float],
        top_k: int,
        filtre: SearchFilter,
    ) -> list[VectorHit]:
        """Cerca vectorial amb filtre obligatori. Retorna fins a `top_k` candidats."""

    @abc.abstractmethod
    def upsert(self, hits: Iterable[VectorHit]) -> int:
        """Inserta/actualitza chunks. Retorna el nombre d'elements escrits."""

    @abc.abstractmethod
    def delete_document(self, doc_id: str, institucio_id: str) -> int:
        """Esborra tots els chunks d'un document. Aïllament: només dins la institució."""

    @abc.abstractmethod
    def health(self) -> dict[str, Any]:
        """Indicador d'estat (per a /api/system/status)."""

    def supports_namespace_isolation(self) -> bool:
        """True si el backend ofereix col·leccions/índexs separats per namespace
        (Qdrant). False si l'aïllament és per filtre dins una sola taula (pgvector)."""
        return False
