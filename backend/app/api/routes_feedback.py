"""Endpoint de feedback (mockup 03: 👍 Útil / 👎 Millorar).

POST /api/feedback → 204.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.schemas import FeedbackRequest
from app.core import audit
from app.core.security import Usuari, get_current_user
from app.db.models import Feedback
from app.db.session import get_db

router = APIRouter(prefix="/api", tags=["feedback"])


@router.post("/feedback", status_code=status.HTTP_204_NO_CONTENT)
def feedback(
    cos: FeedbackRequest,
    usuari: Usuari = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    db.add(
        Feedback(
            message_id=cos.message_id,
            valor=cos.valor,
            comentari=cos.comentari,
            usuari=usuari.usuari,
            institucio_id=usuari.institucio,
        )
    )
    db.commit()
    audit.registra_accio(
        db, usuari=usuari.usuari, rol=usuari.rol.value, accio="feedback",
        detalls={"message_id": cos.message_id, "valor": cos.valor},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
