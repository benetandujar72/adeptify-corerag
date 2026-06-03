"""Endpoint de transcripció de veu (STT local).

POST /api/transcribe  (multipart: fitxer d'àudio) → { "text": "..." }

L'àudio es processa en local amb Whisper; no surt del centre. Queda auditat.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.audio import transcribe
from app.core import audit
from app.core.security import Usuari, get_current_user
from app.db.session import get_db

router = APIRouter(prefix="/api", tags=["veu"])


@router.post("/transcribe")
async def transcriu_audio(
    fitxer: UploadFile = File(...),
    usuari: Usuari = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Transcriu un clip d'àudio (dictat) a text, localment."""
    suffix = Path(fitxer.filename or "audio.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await fitxer.read())
        cami = tmp.name
    try:
        text = transcribe.transcriu(cami)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No s'ha pogut transcriure l'àudio: {exc}",
        )
    finally:
        Path(cami).unlink(missing_ok=True)
    try:
        audit.registra_accio(
            db, usuari=usuari.usuari, rol=usuari.rol.value, accio="transcribe",
            detalls={"chars": len(text)},
        )
    except Exception:
        pass
    return {"text": text}
