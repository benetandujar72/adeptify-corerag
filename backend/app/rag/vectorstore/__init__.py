"""Capa d'abstracció del magatzem vectorial.

Permet canviar de **pgvector** (dev/MVP, dins de PostgreSQL) a **Qdrant**
(producció, vector store dedicat) sense tocar la lògica RAG. La factory tria
el backend a partir de la variable d'entorn `VECTOR_STORE`
(`pgvector` per defecte, `qdrant` per producció).

Decisions clau:
- **Aïllament físic per namespace**: cada document té un `namespace` (p. ex.
  `publico`, `intern`). En Qdrant es tradueix en **col·leccions separades**
  per impossibilitar físicament que el canal públic accedeixi a documents
  interns. En pgvector es manté com a columna + filtre obligatori a la capa
  de dades (mai delegat al prompt).
- **Filtre obligatori a la capa de dades**: l'autoritzaciò es decideix amb
  un `Filter` natiu del backend i s'aplica a la consulta. L'LLM mai veu
  candidats que no estiguin autoritzats.
- **Modular**: afegir un nou backend (p. ex. Pinecone) és implementar
  `VectorStore` i registrar-lo a la factory.
"""

from __future__ import annotations

from app.rag.vectorstore.base import (
    NAMESPACE_INTERN,
    NAMESPACE_PUBLIC,
    SearchFilter,
    VectorHit,
    VectorStore,
)
from app.rag.vectorstore.factory import get_vector_store

__all__ = [
    "NAMESPACE_INTERN",
    "NAMESPACE_PUBLIC",
    "SearchFilter",
    "VectorHit",
    "VectorStore",
    "get_vector_store",
]
