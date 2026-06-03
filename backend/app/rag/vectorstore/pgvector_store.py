"""Implementació `VectorStore` sobre pgvector (PostgreSQL).

Aïllament per namespace: columna `documents.namespace` (per defecte `intern`)
+ filtre obligatori a la consulta. NO és aïllament físic (és el mateix índex),
però el filtre s'aplica SEMPRE a la capa de dades (mai al prompt).

⚠️ Per a producció amb canal públic exposat a Internet, recomanem migrar a
Qdrant (`VECTOR_STORE=qdrant`) que proporciona col·leccions físicament
separades per namespace.
"""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import select, text

from app.db.models import Chunk, Document
from app.db.session import get_sessionmaker
from app.rag.vectorstore.base import SearchFilter, VectorHit, VectorStore


class PgvectorStore(VectorStore):
    """Backend basat en la taula `chunks` amb columna `embedding` (pgvector)."""

    def _construeix_filtres(
        self, filtre: SearchFilter
    ) -> tuple[str, dict[str, Any], list[Any]]:
        """Construeix les condicions WHERE (text + params per a SQL cru) i les
        condicions equivalents en SQLAlchemy (per al cas de no-Postgres).

        Retorna (sql_where, params, sa_conditions).
        """
        sa_conds: list[Any] = []
        sql_parts: list[str] = []
        params: dict[str, Any] = {}

        if filtre.institucio_id is not None:
            sa_conds.append(Document.institucio_id == filtre.institucio_id)
            sql_parts.append("d.institucio_id = :inst")
            params["inst"] = filtre.institucio_id

        if filtre.namespaces is not None:
            ns_list = list(filtre.namespaces)
            sa_conds.append(Document.namespace.in_(ns_list))
            if ns_list:
                marcadors = ", ".join(f":ns{i}" for i in range(len(ns_list)))
                sql_parts.append(f"d.namespace IN ({marcadors})")
                for i, v in enumerate(ns_list):
                    params[f"ns{i}"] = v
            else:
                # llista buida → cap match possible
                sql_parts.append("FALSE")

        if filtre.excloure_visibilitat:
            ex_list = list(filtre.excloure_visibilitat)
            sa_conds.append(~Document.visibilitat.in_(ex_list))
            if ex_list:
                marcadors = ", ".join(f":ex{i}" for i in range(len(ex_list)))
                sql_parts.append(f"d.visibilitat NOT IN ({marcadors})")
                for i, v in enumerate(ex_list):
                    params[f"ex{i}"] = v

        if filtre.doc_ids is not None:
            ids = list(filtre.doc_ids)
            sa_conds.append(Document.doc_id.in_(ids))
            if ids:
                marcadors = ", ".join(f":doc{i}" for i in range(len(ids)))
                sql_parts.append(f"d.doc_id IN ({marcadors})")
                for i, v in enumerate(ids):
                    params[f"doc{i}"] = v
            else:
                sql_parts.append("FALSE")

        sql_where = " AND ".join(sql_parts) if sql_parts else "TRUE"
        return sql_where, params, sa_conds

    def search(
        self,
        vector: list[float],
        top_k: int,
        filtre: SearchFilter,
    ) -> list[VectorHit]:
        # Fail-closed multi-tenant: sense institució acotada NO es retorna res
        # (evita una recuperació oberta cross-tenant si el filtre arriba buit).
        # Coherent amb el comportament de QdrantStore.
        if filtre.institucio_id is None:
            return []
        with get_sessionmaker()() as db:
            _, _, sa_conds = self._construeix_filtres(filtre)
            stmt = select(Chunk, Document).join(Document, Chunk.document_id == Document.id)
            stmt = stmt.where(Chunk.embedding.is_not(None))
            for cond in sa_conds:
                stmt = stmt.where(cond)
            if db.bind is not None and db.bind.dialect.name == "postgresql":
                stmt = stmt.order_by(
                    Chunk.embedding.cosine_distance(vector)  # type: ignore[attr-defined]
                )
            stmt = stmt.limit(top_k)
            files = db.execute(stmt).all()
            return [
                VectorHit(
                    chunk_id=c.id,
                    document_id=d.id,
                    doc_id=d.doc_id,
                    filename=d.filename,
                    tipus=d.tipus,
                    pagina=c.pagina,
                    verificat_el=d.verificat_el,
                    institucio_id=d.institucio_id,
                    namespace=getattr(d, "namespace", "intern"),
                    visibilitat=d.visibilitat,
                    contingut=c.contingut,
                    embedding=c.embedding,
                    score=0.0,
                )
                for c, d in files
            ]

    def upsert(self, hits: Iterable[VectorHit]) -> int:
        # No s'usa des del retriever; la ingesta a pgvector ja és la pipeline
        # ORM existent (`app/ingest/pipeline.py`). Es manté el contracte per
        # compatibilitat amb Qdrant.
        return 0

    def delete_document(self, doc_id: str, institucio_id: str) -> int:
        with get_sessionmaker()() as db:
            d = db.scalar(
                select(Document).where(
                    Document.doc_id == doc_id,
                    Document.institucio_id == institucio_id,
                )
            )
            if d is None:
                return 0
            db.delete(d)
            db.commit()
            return 1

    def health(self) -> dict[str, Any]:
        with get_sessionmaker()() as db:
            try:
                row = db.execute(text("SELECT 1")).scalar()
                return {"backend": "pgvector", "ok": row == 1}
            except Exception as e:  # noqa: BLE001
                return {"backend": "pgvector", "ok": False, "error": str(e)}

    def supports_namespace_isolation(self) -> bool:
        return False  # mateix índex físic, aïllament per filtre obligatori
