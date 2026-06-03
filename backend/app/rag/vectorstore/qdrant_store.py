"""Implementació `VectorStore` sobre Qdrant.

Aïllament FÍSIC per namespace: **cada namespace és una col·lecció diferent**
(p. ex. `centre__publico`, `centre__intern`). Així el canal públic no pot
accedir físicament a la col·lecció interna encara que la lògica falli; el
client només té credencials per la col·lecció que li toca.

A més, dins de cada col·lecció s'aplica un `query_filter` natiu de Qdrant
(`Filter(must=[...])`) amb `institucio_id` i `doc_ids` quan calgui, optimitzat
amb **payload indexes** (keyword) sobre `institucio_id`, `visibilitat` i `doc_id`.

Import diferit del SDK: si `qdrant-client` no està instal·lat (entorn dev),
l'única operació no fallida és `health()` (retorna `ok=False`). Així no
trenquem els tests existents.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Iterable

from app.rag.vectorstore.base import SearchFilter, VectorHit, VectorStore

_log = logging.getLogger(__name__)


def _coll(institucio: str, namespace: str) -> str:
    """Nom de la col·lecció: `<inst>__<namespace>`. Format alfanumèric i `_`."""
    inst = "".join(c if c.isalnum() else "_" for c in institucio.lower())
    ns = "".join(c if c.isalnum() else "_" for c in namespace.lower())
    return f"{inst}__{ns}"


class QdrantStore(VectorStore):
    """Backend Qdrant (col·leccions separades per (institucio, namespace))."""

    def __init__(self, url: str | None = None, api_key: str | None = None, dim: int = 1024) -> None:
        self._url = url or os.environ.get("QDRANT_URL", "http://qdrant:6333")
        self._api_key = api_key or os.environ.get("QDRANT_API_KEY") or None
        self._dim = dim
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from qdrant_client import QdrantClient  # type: ignore

                self._client = QdrantClient(url=self._url, api_key=self._api_key, timeout=10.0)
            except Exception as exc:  # noqa: BLE001
                _log.warning("Qdrant SDK no disponible: %s", exc)
                self._client = None
        return self._client

    def _assegura_coleccio(self, nom: str) -> bool:
        client = self._get_client()
        if client is None:
            return False
        try:
            from qdrant_client.http import models as qmodels  # type: ignore

            cols = {c.name for c in client.get_collections().collections}
            if nom in cols:
                return True
            client.create_collection(
                collection_name=nom,
                vectors_config=qmodels.VectorParams(
                    size=self._dim, distance=qmodels.Distance.COSINE
                ),
            )
            # Payload indexes (keyword) per accelerar el filtre: institucio_id,
            # visibilitat, doc_id, namespace.
            for camp in ("institucio_id", "visibilitat", "doc_id", "namespace"):
                try:
                    client.create_payload_index(
                        collection_name=nom,
                        field_name=camp,
                        field_schema=qmodels.PayloadSchemaType.KEYWORD,
                    )
                except Exception:  # idempotent
                    pass
            return True
        except Exception as exc:  # noqa: BLE001
            _log.warning("Qdrant: no s'ha pogut assegurar la col·lecció %s: %s", nom, exc)
            return False

    def _build_filter(self, filtre: SearchFilter):
        """Construeix el `Filter(must=[...])` natiu de Qdrant a partir del filtre genèric."""
        try:
            from qdrant_client.http import models as qmodels  # type: ignore
        except Exception:
            return None
        must: list[Any] = []
        if filtre.institucio_id is not None:
            must.append(
                qmodels.FieldCondition(
                    key="institucio_id",
                    match=qmodels.MatchValue(value=filtre.institucio_id),
                )
            )
        if filtre.doc_ids:
            must.append(
                qmodels.FieldCondition(
                    key="doc_id",
                    match=qmodels.MatchAny(any=list(filtre.doc_ids)),
                )
            )
        must_not: list[Any] = []
        for v in filtre.excloure_visibilitat or ():
            must_not.append(
                qmodels.FieldCondition(
                    key="visibilitat",
                    match=qmodels.MatchValue(value=v),
                )
            )
        return qmodels.Filter(must=must or None, must_not=must_not or None)

    def search(
        self,
        vector: list[float],
        top_k: int,
        filtre: SearchFilter,
    ) -> list[VectorHit]:
        client = self._get_client()
        if client is None:
            return []
        # Aïllament FÍSIC: una col·lecció per (institucio, namespace).
        if filtre.institucio_id is None or not filtre.namespaces:
            # Sense aquests dos paràmetres no podem decidir la col·lecció:
            # FAIL CLOSED — no retornem res (millor que retornar massa).
            return []
        query_filter = self._build_filter(filtre)
        resultats: list[VectorHit] = []
        for ns in filtre.namespaces:
            coll = _coll(filtre.institucio_id, ns)
            try:
                punts = client.search(
                    collection_name=coll,
                    query_vector=vector,
                    query_filter=query_filter,
                    limit=top_k,
                    with_payload=True,
                    with_vectors=False,
                )
            except Exception as exc:  # noqa: BLE001
                _log.warning("Qdrant search KO a %s: %s", coll, exc)
                continue
            for p in punts:
                payload = p.payload or {}
                resultats.append(
                    VectorHit(
                        chunk_id=str(p.id),
                        document_id=payload.get("document_id", ""),
                        doc_id=payload.get("doc_id", ""),
                        filename=payload.get("filename", ""),
                        tipus=payload.get("tipus", ""),
                        pagina=payload.get("pagina"),
                        verificat_el=payload.get("verificat_el"),
                        institucio_id=payload.get("institucio_id", ""),
                        namespace=payload.get("namespace", ns),
                        visibilitat=payload.get("visibilitat", "tots"),
                        contingut=payload.get("contingut", ""),
                        embedding=None,
                        score=float(getattr(p, "score", 0.0) or 0.0),
                    )
                )
        # Si hem cercat en múltiples col·leccions, ordenem per puntuació i limitem.
        resultats.sort(key=lambda h: h.score, reverse=True)
        return resultats[:top_k]

    def upsert(self, hits: Iterable[VectorHit]) -> int:
        client = self._get_client()
        if client is None:
            return 0
        try:
            from qdrant_client.http import models as qmodels  # type: ignore
        except Exception:
            return 0
        n = 0
        # Agrupem per col·lecció per fer batches eficients.
        per_coll: dict[str, list[Any]] = {}
        for h in hits:
            if not h.embedding:
                continue
            coll = _coll(h.institucio_id, h.namespace)
            self._assegura_coleccio(coll)
            per_coll.setdefault(coll, []).append(
                qmodels.PointStruct(
                    id=h.chunk_id,
                    vector=list(h.embedding),
                    payload={
                        "document_id": h.document_id,
                        "doc_id": h.doc_id,
                        "filename": h.filename,
                        "tipus": h.tipus,
                        "pagina": h.pagina,
                        "verificat_el": h.verificat_el,
                        "institucio_id": h.institucio_id,
                        "namespace": h.namespace,
                        "visibilitat": h.visibilitat,
                        "contingut": h.contingut,
                    },
                )
            )
        for coll, pts in per_coll.items():
            try:
                client.upsert(collection_name=coll, points=pts)
                n += len(pts)
            except Exception as exc:  # noqa: BLE001
                _log.warning("Qdrant upsert KO a %s: %s", coll, exc)
        return n

    def delete_document(self, doc_id: str, institucio_id: str) -> int:
        client = self._get_client()
        if client is None:
            return 0
        try:
            from qdrant_client.http import models as qmodels  # type: ignore
        except Exception:
            return 0
        n = 0
        # Esborrem el doc de TOTES les col·leccions de la institució (per si està
        # repartit en namespaces).
        try:
            cols = [c.name for c in client.get_collections().collections]
        except Exception:
            return 0
        prefix = "".join(ch if ch.isalnum() else "_" for ch in institucio_id.lower()) + "__"
        for coll in cols:
            if not coll.startswith(prefix):
                continue
            try:
                resp = client.delete(
                    collection_name=coll,
                    points_selector=qmodels.FilterSelector(
                        filter=qmodels.Filter(
                            must=[
                                qmodels.FieldCondition(
                                    key="doc_id",
                                    match=qmodels.MatchValue(value=doc_id),
                                ),
                                qmodels.FieldCondition(
                                    key="institucio_id",
                                    match=qmodels.MatchValue(value=institucio_id),
                                ),
                            ]
                        )
                    ),
                )
                n += getattr(resp, "operation_id", 0) and 1 or 0
            except Exception as exc:  # noqa: BLE001
                _log.warning("Qdrant delete KO a %s: %s", coll, exc)
        return n

    def health(self) -> dict[str, Any]:
        client = self._get_client()
        if client is None:
            return {"backend": "qdrant", "ok": False, "error": "SDK no disponible"}
        try:
            cols = client.get_collections().collections
            return {"backend": "qdrant", "ok": True, "n_colleccions": len(cols)}
        except Exception as exc:  # noqa: BLE001
            return {"backend": "qdrant", "ok": False, "error": str(exc)}

    def supports_namespace_isolation(self) -> bool:
        return True  # col·leccions separades físicament per (inst, namespace)
