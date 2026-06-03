"""Endpoints de documents i ingesta.

GET  /api/documents       → documents indexats (amb estat).
POST /api/ingest          → encua una ingesta (multipart o { "path": "…" }).
GET  /api/ingest/{job_id} → estat d'una ingesta.

La ingesta reutilitza el mateix codi que el seed (app/ingest/pipeline.py).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    DocumentEstat,
    DocumentsResponse,
    IngestResponse,
    IngestStatusResponse,
)
from app.core import audit
from app.core.config import get_settings
from app.core.roles import Rol
from app.core.security import Usuari, get_current_user
from app.db.models import Document, DocumentOriginal
from app.db.session import get_db, get_sessionmaker
from app.ingest import loaders, pipeline

router = APIRouter(prefix="/api", tags=["documents"])

# Rols que poden veure documentació de gestió (visibilitat "admin").
_ROLS_ADMIN_DOC = {Rol.DIRECCIO, Rol.PAS, Rol.SUPERADMIN}

# Rols autoritzats a INGERIR documents (afegeixen coneixement a la institució).
_ROLS_INGESTA = {Rol.DIRECCIO, Rol.PAS, Rol.SUPERADMIN, Rol.DOCENT}

# Mida màxima d'un fitxer pujat (anti zip-bomb / exhauriment de disc i memòria).
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB


@router.get("/documents", response_model=DocumentsResponse)
def llista_documents(
    usuari: Usuari = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentsResponse:
    docs = db.scalars(
        select(Document)
        .where(Document.institucio_id == usuari.institucio)
        .order_by(Document.filename)
    ).all()
    return DocumentsResponse(
        documents=[
            DocumentEstat(
                doc_id=d.doc_id,
                filename=d.filename,
                tipus=d.tipus,  # type: ignore[arg-type]
                fragments=d.n_chunks,
                verificat_el=d.verificat_el,
                estat=d.estat,
                origen=d.origen,
                canal_rag=d.canal_rag,
                sensibilitat=d.sensibilitat,
                exportable_ia=d.exportable_ia,
                metadades=d.metadades,
            )
            for d in docs
        ]
    )


@router.get("/documents/{doc_id}/descarrega")
def descarrega_document(
    doc_id: str,
    usuari: Usuari = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Descarrega/obre el fitxer ORIGINAL d'una font citada (F1, docs/20).

    Aïllament: només documents de la PRÒPIA institució (cross-tenant → 404). Respecta
    la visibilitat "admin" (només direcció/PAS/superadmin). Tot auditat. Si no se'n va
    desar l'original (ingerit abans de F1 o massa gran) → 404.
    """
    doc = db.scalar(
        select(Document).where(
            Document.doc_id == doc_id, Document.institucio_id == usuari.institucio
        )
    )
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document no trobat.")
    if doc.visibilitat == "admin" and usuari.rol not in _ROLS_ADMIN_DOC:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Aquest document és de gestió interna (només direcció/PAS).",
        )
    orig = db.get(DocumentOriginal, doc_id)
    if orig is None or orig.institucio_id != usuari.institucio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="L'original no està disponible per a aquest document.",
        )
    audit.registra_accio(
        db, usuari=usuari.usuari, rol=usuari.rol.value, accio="document_download",
        detalls={"doc_id": doc_id, "institucio": usuari.institucio},
    )
    nom = (orig.filename or doc_id).replace('"', "").replace("\n", " ")
    return Response(
        content=orig.contingut,
        media_type=orig.mime or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{nom}"'},
    )


def _executa_en_rerefons(job_id: str, carpeta: str | None) -> None:
    """Tasca de fons: obre una sessió pròpia i executa la ingesta."""
    job = pipeline.get_job(job_id)
    if job is None:
        return
    sessio = get_sessionmaker()()
    try:
        pipeline.executa_job(job, sessio, carpeta)
    finally:
        sessio.close()


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest(
    background: BackgroundTasks,
    fitxer: UploadFile | None = File(default=None),
    path: str | None = None,
    usuari: Usuari = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IngestResponse:
    """Encua una ingesta. Accepta un fitxer (multipart) o una ruta de carpeta."""
    # RBAC: només rols de gestió/docència poden afegir coneixement a la institució
    # (abans qualsevol usuari autenticat, inclòs alumne/família, podia ingerir).
    if usuari.rol not in _ROLS_INGESTA:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El teu rol no està autoritzat a ingerir documents.",
        )
    settings = get_settings()
    job = pipeline.crea_job(usuari.institucio)  # job lligat a la institució del caller

    audit.registra_accio(
        db,
        usuari=usuari.usuari,
        rol=usuari.rol.value,
        accio="ingest",
        detalls={"path": path, "fitxer": fitxer.filename if fitxer else None},
    )

    if fitxer is not None:
        # Desa el fitxer pujat conservant el NOM ORIGINAL (el doc_id i el
        # filename se'n deriven) dins un directori temporal, i ingereix-lo en
        # primer pla (un sol fitxer és ràpid); marca el job com a fet.
        nom_original = Path(fitxer.filename or "document").name
        if loaders.tipus_de(Path(nom_original)) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tipus de fitxer no suportat: {Path(nom_original).suffix}",
            )
        # Límit de mida (anti zip-bomb / exhauriment). Comprovem la mida declarada
        # i, com a defensa, també els bytes realment llegits.
        if fitxer.size is not None and fitxer.size > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="El fitxer supera la mida màxima permesa (100 MB).",
            )
        with tempfile.TemporaryDirectory() as carpeta_tmp:
            desti = Path(carpeta_tmp) / nom_original
            dades = await fitxer.read()
            if len(dades) > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="El fitxer supera la mida màxima permesa (100 MB).",
                )
            desti.write_bytes(dades)
            docs, chunks = pipeline.ingesta_fitxer(
                db, desti, institucio_id=usuari.institucio
            )
        job.estat = "fet"
        job.documents = docs
        job.chunks = chunks
        return IngestResponse(job_id=job.job_id, estat=job.estat)

    # Ingesta de carpeta en segon pla. La ruta es CONTÉ sempre dins de
    # SAMPLE_DATA_PATH: evita travessa de directoris / lectura arbitrària del
    # sistema de fitxers del contenidor i el rglob sobre arbres enormes (DoS).
    base = Path(settings.sample_data_path).resolve()
    if path:
        candidata = (base / path).resolve()
        if candidata != base and not candidata.is_relative_to(base):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ruta d'ingesta no permesa (ha d'estar dins de sample_data).",
            )
        carpeta = str(candidata)
    else:
        carpeta = str(base)
    background.add_task(_executa_en_rerefons, job.job_id, carpeta)
    return IngestResponse(job_id=job.job_id, estat="encuat")


@router.delete("/documents/{doc_id}")
def esborra_document(
    doc_id: str,
    usuari: Usuari = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Esborra un document indexat (i els seus chunks) de la biblioteca."""
    # Aïllament multi-tenant: només es pot esborrar un document de la PRÒPIA
    # institució. Si és d'un altre centre (o no existeix) → 404 (no revela existència).
    doc = db.scalar(
        select(Document).where(
            Document.doc_id == doc_id, Document.institucio_id == usuari.institucio
        )
    )
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document no trobat."
        )
    existia = pipeline.elimina_document(db, doc_id)
    audit.registra_accio(
        db,
        usuari=usuari.usuari,
        rol=usuari.rol.value,
        accio="document_delete",
        detalls={"doc_id": doc_id, "institucio": usuari.institucio, "existia": existia},
    )
    if not existia:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document no trobat."
        )
    return {"esborrat": True, "doc_id": doc_id}


@router.get("/ingest/{job_id}", response_model=IngestStatusResponse)
def estat_ingest(
    job_id: str,
    usuari: Usuari = Depends(get_current_user),
) -> IngestStatusResponse:
    job = pipeline.get_job(job_id)
    # Aïllament: només el propi centre pot consultar l'estat del seu job.
    if job is None or job.institucio_id != usuari.institucio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job d'ingesta no trobat."
        )
    return IngestStatusResponse(
        estat=job.estat,  # type: ignore[arg-type]
        documents=job.documents,
        chunks=job.chunks,
        detall=job.detall,
    )
