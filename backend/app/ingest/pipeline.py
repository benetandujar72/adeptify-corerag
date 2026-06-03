"""Pipeline d'ingesta: carpeta → loaders → chunking → embeddings → pgvector.

La ingesta llegeix genèricament una carpeta (per defecte `/app/sample_data`,
muntada read-only) i indexa qualsevol fitxer amb extensió suportada. NO es
codifiquen noms de fitxer concrets.

Inclou un registre de jobs en memòria per donar suport a
`POST /api/ingest` → `GET /api/ingest/{job_id}`.
"""

from __future__ import annotations

import datetime as dt
import logging
import mimetypes
import re
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Chunk as ChunkRow
from app.db.models import Document, DocumentOriginal
from app.ingest import loaders
from app.ingest.chunking import chunk_pagines
from app.rag.embeddings import get_embedder

# Mida màxima de l'original que es desa per a descàrrega (F1). Per damunt, no es
# desa el blob (el RAG segueix funcionant; només no s'ofereix la descàrrega).
_MAX_ORIGINAL_BYTES = 25 * 1024 * 1024  # 25 MB

_MIME_PER_TIPUS = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "md": "text/markdown; charset=utf-8",
    "html": "text/html; charset=utf-8",
}


def _desa_original(
    db: Session, doc_id: str, institucio_id: str, cami: Path, tipus: str
) -> None:
    """Desa (o actualitza) el fitxer original per a poder-lo descarregar després.

    Best-effort: si falla la lectura o supera la mida màxima, no bloqueja la ingesta.
    """
    try:
        dades = cami.read_bytes()
        if not dades or len(dades) > _MAX_ORIGINAL_BYTES:
            return
        mime = _MIME_PER_TIPUS.get(tipus) or mimetypes.guess_type(cami.name)[0] \
            or "application/octet-stream"
        existent = db.get(DocumentOriginal, doc_id)
        if existent is not None:
            existent.institucio_id = institucio_id
            existent.filename = cami.name
            existent.mime = mime
            existent.mida = len(dades)
            existent.contingut = dades
        else:
            db.add(DocumentOriginal(
                doc_id=doc_id, institucio_id=institucio_id, filename=cami.name,
                mime=mime, mida=len(dades), contingut=dades,
            ))
    except Exception:  # noqa: BLE001 - desar l'original no ha de trencar la ingesta
        pass


# ───────────────────────── Registre de jobs ─────────────────────────────────


@dataclass
class JobIngesta:
    """Estat d'una tasca d'ingesta."""

    job_id: str
    estat: str = "encuat"  # encuat | processant | fet | error
    documents: int = 0
    chunks: int = 0
    detall: str | None = None
    institucio_id: str = "nou_patufet"  # tenant propietari (aïllament de l'estat del job)


_jobs: dict[str, JobIngesta] = {}
_jobs_lock = threading.Lock()


def crea_job(institucio_id: str = "nou_patufet") -> JobIngesta:
    job = JobIngesta(job_id=uuid.uuid4().hex, institucio_id=institucio_id)
    with _jobs_lock:
        _jobs[job.job_id] = job
    return job


def get_job(job_id: str) -> JobIngesta | None:
    with _jobs_lock:
        return _jobs.get(job_id)


def _actualitza_job(job: JobIngesta, **camps) -> None:
    with _jobs_lock:
        for k, v in camps.items():
            setattr(job, k, v)


# ───────────────────────── Ingesta d'un document ────────────────────────────


def _slug(filename: str) -> str:
    """Deriva un doc_id estable a partir del nom de fitxer."""
    base = Path(filename).stem.lower()
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")
    return base or uuid.uuid4().hex


def ingesta_fitxer(
    db: Session,
    cami: Path,
    versio: str = "1",
    institucio_id: str = "nou_patufet",
    visibilitat: str = "tots",
    origen: str = "manual",
    canal_rag: str = "rag_materials_docents",
    sensibilitat: str | None = None,
    exportable_ia: bool | None = None,
    metadades: dict | None = None,
) -> tuple[int, int]:
    """Ingereix un únic fitxer. Retorna (documents_nous, chunks_creats).

    Si el document ja existeix (mateix doc_id), es reindexa: s'esborren els
    chunks antics i es torna a indexar amb la versió indicada. El document
    s'assigna a la institució `institucio_id` (tenant). `visibilitat` controla
    qui el pot recuperar al RAG ("tots" o "admin").
    """
    tipus = loaders.tipus_de(cami)
    if tipus is None:
        return (0, 0)

    pagines = loaders.carrega(cami)
    chunks = chunk_pagines(pagines)
    if not chunks:
        return (0, 0)

    classificacio = None
    # DLP + classificació RAG/CAG: NO bloqueja la indexació (best-effort), però
    # etiqueta el document i bloqueja `exportable_ia` si hi ha dades personals,
    # menors, avaluacions o informació educativa sensible.
    try:
        from app.security import content_safety, dlp

        coincidencies = dlp.escaneja_textos(c.contingut for c in chunks)
        severitat = dlp.resum_severitat(coincidencies)
        classificacio = content_safety.classifica_textos(
            (c.contingut for c in chunks), origen=origen
        )
        if severitat != "ok":
            from collections import Counter

            per_tipus = Counter(c.tipus for c in coincidencies)
            logging.getLogger(__name__).warning(
                "DLP ingesta: fitxer=%s institucio=%s severitat=%s tipus=%s",
                cami.name, institucio_id, severitat, dict(per_tipus),
            )
    except Exception:  # noqa: BLE001 - el DLP no ha de trencar mai la ingesta
        pass
    sensibilitat_final = sensibilitat or (classificacio.sensibilitat if classificacio else "docent")
    exportable_final = (
        bool(exportable_ia)
        if exportable_ia is not None
        else bool(classificacio.exportable_ia if classificacio else False)
    )
    if classificacio is not None and not classificacio.exportable_ia:
        exportable_final = False
    meta_final = dict(metadades or {})
    if classificacio is not None:
        meta_final.setdefault("classificacio", {
            "severitat_dlp": classificacio.severitat_dlp,
            "motius": classificacio.motius,
            "deteccions": classificacio.deteccions,
        })

    embedder = get_embedder()
    vectors = embedder.embed([c.contingut for c in chunks])

    doc_id = _slug(cami.name)
    verificat_el = dt.date.today().isoformat()

    existent = db.scalar(select(Document).where(Document.doc_id == doc_id))
    if existent is not None:
        db.execute(delete(ChunkRow).where(ChunkRow.document_id == existent.id))
        document = existent
        document.filename = cami.name
        document.tipus = tipus
        document.versio = versio
        document.verificat_el = verificat_el
        document.n_chunks = len(chunks)
        document.estat = "indexat"
        document.institucio_id = institucio_id
        document.visibilitat = visibilitat
        document.origen = origen
        document.canal_rag = canal_rag
        document.sensibilitat = sensibilitat_final
        document.exportable_ia = exportable_final
        document.metadades = meta_final
        document_nou = 0
    else:
        document = Document(
            doc_id=doc_id,
            filename=cami.name,
            tipus=tipus,
            versio=versio,
            verificat_el=verificat_el,
            n_chunks=len(chunks),
            estat="indexat",
            institucio_id=institucio_id,
            visibilitat=visibilitat,
            origen=origen,
            canal_rag=canal_rag,
            sensibilitat=sensibilitat_final,
            exportable_ia=exportable_final,
            metadades=meta_final,
        )
        db.add(document)
        db.flush()  # per obtenir document.id
        document_nou = 1

    for chunk, vector in zip(chunks, vectors):
        db.add(
            ChunkRow(
                document_id=document.id,
                contingut=chunk.contingut,
                pagina=chunk.pagina,
                ordre=chunk.ordre,
                embedding=vector,
            )
        )
    # Desa l'original per a poder obrir/descarregar la font citada (F1, docs/20).
    _desa_original(db, doc_id, institucio_id, cami, tipus)
    db.commit()
    return (document_nou, len(chunks))


def elimina_document(db: Session, doc_id: str) -> bool:
    """Esborra un document i tots els seus chunks. Retorna True si existia."""
    doc = db.scalar(select(Document).where(Document.doc_id == doc_id))
    if doc is None:
        return False
    db.execute(delete(ChunkRow).where(ChunkRow.document_id == doc.id))
    db.execute(delete(DocumentOriginal).where(DocumentOriginal.doc_id == doc_id))
    db.delete(doc)
    db.commit()
    return True


def ingesta_carpeta(
    db: Session,
    carpeta: str | Path | None = None,
    institucio_id: str = "nou_patufet",
) -> tuple[int, int]:
    """Ingereix tots els fitxers suportats d'una carpeta (recursivament).

    Retorna (documents, chunks) totals. La carpeta per defecte és la de
    `sample_data` configurada. Tots els documents s'assignen a `institucio_id`
    (aïllament multi-tenant: abans queien sempre a la institució per defecte).
    """
    arrel = Path(carpeta) if carpeta else Path(get_settings().sample_data_path)
    if not arrel.exists():
        raise FileNotFoundError(f"La carpeta d'ingesta no existeix: {arrel}")

    total_docs = 0
    total_chunks = 0
    for cami in sorted(arrel.rglob("*")):
        if cami.is_file() and loaders.tipus_de(cami) is not None:
            docs, chunks = ingesta_fitxer(db, cami, institucio_id=institucio_id)
            total_docs += docs
            total_chunks += chunks
    return (total_docs, total_chunks)


def executa_job(job: JobIngesta, db: Session, carpeta: str | Path | None) -> None:
    """Executa una ingesta de carpeta dins d'un job, actualitzant-ne l'estat."""
    _actualitza_job(job, estat="processant")
    try:
        # Propaga la institució del job (aïllament multi-tenant).
        docs, chunks = ingesta_carpeta(db, carpeta, institucio_id=job.institucio_id)
        _actualitza_job(job, estat="fet", documents=docs, chunks=chunks)
    except Exception:  # noqa: BLE001 - registrem qualsevol fallada al job
        # No exposem el detall de l'excepció al client (GET /api/ingest/{job_id}).
        logging.getLogger(__name__).exception("Ingesta de carpeta KO (job=%s)", job.job_id)
        _actualitza_job(job, estat="error", detall="error_ingesta")
