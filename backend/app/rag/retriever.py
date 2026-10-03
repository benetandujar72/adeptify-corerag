"""Retrieval RAG: embed pregunta → top-k pgvector → rerank → top-n.

El resultat és una llista de `ResultatRetrieval` (chunk + metadades del seu
document) i un agregat de `Font` per al contracte. El filtratge per rol (RBAC
de documents) s'aplica abans del rerank.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.schemas import Font
from app.core.config import get_settings
from app.db.models import Chunk, Document
from app.rag.embeddings import get_embedder
from app.rag.rerank import CandidatRerank, get_reranker


@dataclass
class ResultatRetrieval:
    """Un chunk recuperat amb les metadades del seu document i la seva puntuació."""

    doc_id: str
    filename: str
    tipus: str
    pagina: int | None
    verificat_el: str | None
    contingut: str
    score: float


def _cerca_vectorial(
    db: Session,
    vector: list[float],
    top_k: int,
    institucio_id: str | None = None,
    incloure_admin: bool = True,
    coneixement_doc_ids: set[str] | None = None,
    namespaces: set[str] | None = None,
) -> list[tuple[Chunk, Document]]:
    """Cerca els top-k chunks per similitud cosinus a pgvector.

    A Postgres s'ordena per l'operador de distància cosinus (`<=>`). En altres
    dialectes (p. ex. SQLite en tests, sense l'operador) es retorna sense ordre
    vectorial; el rerank posterior reordena els candidats igualment.

    Si s'indica `institucio_id`, només es recuperen chunks de documents d'aquesta
    institució (aïllament multi-tenant). Si s'indica `coneixement_doc_ids`, la cerca
    es limita a aquests documents (coneixement propi d'un skill, P3) ABANS del top-k.
    Si s'indica `namespaces`, només es retornen chunks de documents amb un d'aquests
    namespaces (aïllament canal públic vs. canal intern).
    """
    stmt = select(Chunk, Document).join(Document, Chunk.document_id == Document.id)
    stmt = stmt.where(Chunk.embedding.is_not(None),
                      Document.sensibilitat.in_(("public", "docent", "intern")))
    if institucio_id is not None:
        stmt = stmt.where(Document.institucio_id == institucio_id)
    if not incloure_admin:
        stmt = stmt.where(Document.visibilitat != "admin")
    if coneixement_doc_ids is not None:
        stmt = stmt.where(Document.doc_id.in_(coneixement_doc_ids))
    if namespaces is not None:
        stmt = stmt.where(Document.namespace.in_(list(namespaces)))
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        stmt = stmt.order_by(
            Chunk.embedding.cosine_distance(vector)  # type: ignore[attr-defined]
        )
    stmt = stmt.limit(top_k)
    return list(db.execute(stmt).all())


def _cerca_lexica(
    db: Session,
    query: str,
    top_k: int,
    institucio_id: str | None = None,
    incloure_admin: bool = True,
    coneixement_doc_ids: set[str] | None = None,
    namespaces: set[str] | None = None,
) -> list[tuple[Chunk, Document]]:
    """Cerca lèxica full-text (estil BM25) amb el motor de Postgres.

    Captura coincidències exactes de termes, noms i dates que la cerca semàntica
    pot passar per alt. Només disponible a Postgres; en altres dialectes retorna [].
    Filtra per `institucio_id` (aïllament) i per `coneixement_doc_ids` (skill, P3) si
    s'indiquen.
    """
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return []
    # Construïm el filtre d'institució condicionalment (evitem `:inst IS NULL`,
    # que a Postgres dona "could not determine data type of parameter").
    filtre_inst = ""
    params: dict = {"q": query, "k": top_k}
    if institucio_id is not None:
        filtre_inst = " AND d.institucio_id = :inst"
        params["inst"] = institucio_id
    filtre_vis = " AND d.sensibilitat IN ('public', 'docent', 'intern')"
    if not incloure_admin:
        filtre_vis += " AND d.visibilitat <> 'admin'"
    # Coneixement propi de l'skill: limita als doc_ids indicats (parametritzat).
    filtre_con = ""
    if coneixement_doc_ids is not None:
        ids = list(coneixement_doc_ids)
        marcadors = ", ".join(f":con{i}" for i in range(len(ids)))
        # Sense documents → cap resultat possible (evita un IN buit invàlid).
        if not ids:
            return []
        filtre_con = f" AND d.doc_id IN ({marcadors})"
        for i, v in enumerate(ids):
            params[f"con{i}"] = v
    # Namespace (canal públic vs. canal intern). Aplicat a la capa de dades.
    filtre_ns = ""
    if namespaces is not None:
        ns_list = list(namespaces)
        if not ns_list:
            return []
        ns_marc = ", ".join(f":ns{i}" for i in range(len(ns_list)))
        filtre_ns = f" AND d.namespace IN ({ns_marc})"
        for i, v in enumerate(ns_list):
            params[f"ns{i}"] = v
    sql = text(
        f"""
        SELECT c.id
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE to_tsvector('simple', c.contingut)
              @@ plainto_tsquery('simple', :q){filtre_inst}{filtre_vis}{filtre_con}{filtre_ns}
        ORDER BY ts_rank(
            to_tsvector('simple', c.contingut),
            plainto_tsquery('simple', :q)
        ) DESC
        LIMIT :k
        """
    )
    try:
        ids = [row[0] for row in db.execute(sql, params).all()]
    except Exception:
        # No deixem la transacció en estat avortat (poisoning de la sessió).
        db.rollback()
        return []
    if not ids:
        return []
    # Carrega els chunks (amb el seu document) preservant l'ordre del ranking lèxic.
    files = db.execute(
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.id.in_(ids))
    ).all()
    per_id = {c.id: (c, d) for c, d in files}
    return [per_id[i] for i in ids if i in per_id]


def _fusiona_rrf(
    llistes: list[list[tuple[Chunk, Document]]], k: int = 60
) -> list[tuple[Chunk, Document]]:
    """Reciprocal Rank Fusion: combina diverses llistes ordenades en una de sola."""
    punts: dict = {}
    objs: dict = {}
    for llista in llistes:
        for rang, (chunk, doc) in enumerate(llista):
            punts[chunk.id] = punts.get(chunk.id, 0.0) + 1.0 / (k + rang + 1)
            objs[chunk.id] = (chunk, doc)
    return sorted(objs.values(), key=lambda cd: punts[cd[0].id], reverse=True)


def _ordena_per_cosinus(
    vector: list[float],
    permesos: list[tuple[Chunk, Document]],
    candidats: list[CandidatRerank],
    top_n: int,
) -> list[tuple[CandidatRerank, float]]:
    """Ordena els candidats per similitud cosinus (mode ràpid, sense reranker)."""
    import numpy as np

    qv = np.asarray(vector, dtype=np.float32)
    qn = float(np.linalg.norm(qv)) or 1.0
    puntuats: list[tuple[CandidatRerank, float]] = []
    for (chunk, _doc), candidat in zip(permesos, candidats):
        emb = chunk.embedding
        if emb is None:
            sim = 0.0
        else:
            ev = np.asarray(emb, dtype=np.float32)
            en = float(np.linalg.norm(ev)) or 1.0
            sim = float(np.dot(qv, ev) / (qn * en))
        puntuats.append((candidat, round(sim, 4)))
    puntuats.sort(key=lambda x: x[1], reverse=True)
    return puntuats[:top_n]


def retrieve(
    db: Session,
    pregunta: str,
    *,
    doc_ids_permesos: set[str] | None = None,
    top_k: int | None = None,
    top_n: int | None = None,
    institucio_id: str | None = None,
    incloure_admin: bool = True,
    coneixement_doc_ids: set[str] | None = None,
    namespaces: set[str] | None = None,
) -> list[ResultatRetrieval]:
    """Executa el pipeline complet de retrieval per a una pregunta.

    `doc_ids_permesos`, si s'indica, restringeix els documents accessibles segons
    el rol de l'usuari (RBAC de documents). `coneixement_doc_ids`, si s'indica,
    limita la cerca al coneixement propi d'un skill (P3): si és un conjunt buit,
    no es recupera res (l'skill té coneixement però cap document encara hi encaixa).
    `namespaces`: aïllament per canal (p. ex. {'publico'} per al canal públic web).
    """
    # Un context sense centre no autoritza una cerca global, ni tan sols interna.
    if not institucio_id:
        return []
    # L'ACL s'aplica abans del top-k i de carregar contingut, no només després.
    if doc_ids_permesos is not None:
        coneixement_doc_ids = (
            set(doc_ids_permesos) if coneixement_doc_ids is None
            else set(coneixement_doc_ids) & doc_ids_permesos
        )
        if not coneixement_doc_ids:
            return []
    settings = get_settings()
    top_k = top_k or settings.rag_top_k
    top_n = top_n or settings.rag_top_n

    vector = get_embedder().embed_query(pregunta)
    vec_hits = _cerca_vectorial(
        db, vector, top_k, institucio_id, incloure_admin, coneixement_doc_ids, namespaces
    )

    if settings.hybrid_actiu:
        # Híbrid: fusiona semàntic (vector) + lèxic (full-text) via RRF. Millora
        # el recall en termes exactes, noms i dates. El reranker decideix l'ordre final.
        lex_hits = _cerca_lexica(
            db, pregunta, top_k, institucio_id, incloure_admin, coneixement_doc_ids, namespaces
        )
        files = _fusiona_rrf([vec_hits, lex_hits])[:top_k] if lex_hits else vec_hits
    else:
        files = vec_hits

    # RBAC de documents conservant l'ordre (pgvector ja ordena per cosinus).
    permesos = [
        (chunk, document)
        for chunk, document in files
        if doc_ids_permesos is None or document.doc_id in doc_ids_permesos
    ]
    candidats: list[CandidatRerank] = [
        CandidatRerank(
            text=chunk.contingut,
            payload={
                "doc_id": document.doc_id,
                "filename": document.filename,
                "tipus": document.tipus,
                "pagina": chunk.pagina,
                "verificat_el": document.verificat_el,
                "contingut": chunk.contingut,
            },
        )
        for chunk, document in permesos
    ]

    if settings.reranker_actiu:
        reordenats = get_reranker().rerank(pregunta, candidats, top_n)
    else:
        # Mode ràpid: sense reranker (el coll d'ampolla en CPU). Puntuació =
        # similitud cosinus amb la pregunta sobre els embeddings emmagatzemats.
        reordenats = _ordena_per_cosinus(vector, permesos, candidats, top_n)
    resultats: list[ResultatRetrieval] = []
    for candidat, score in reordenats:
        p = candidat.payload
        resultats.append(
            ResultatRetrieval(
                doc_id=p["doc_id"],
                filename=p["filename"],
                tipus=p["tipus"],
                pagina=p["pagina"],
                verificat_el=p["verificat_el"],
                contingut=p["contingut"],
                score=round(score, 4),
            )
        )
    return resultats


def agrega_fonts(resultats: list[ResultatRetrieval]) -> list[Font]:
    """Agrega els resultats en `Font` per document (panell dret del dashboard)."""
    per_doc: dict[str, list[ResultatRetrieval]] = defaultdict(list)
    for r in resultats:
        per_doc[r.doc_id].append(r)

    fonts: list[Font] = []
    for doc_id, items in per_doc.items():
        millor = max(items, key=lambda x: x.score)
        fonts.append(
            Font(
                doc_id=doc_id,
                filename=millor.filename,
                tipus=millor.tipus,  # type: ignore[arg-type]
                pagina=millor.pagina,
                fragments=len(items),
                score=millor.score,
                verificat_el=millor.verificat_el,
                snippet=millor.contingut[:240],
            )
        )
    fonts.sort(key=lambda f: f.score, reverse=True)
    return fonts
