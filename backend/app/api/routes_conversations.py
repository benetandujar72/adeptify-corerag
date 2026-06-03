"""Endpoints de converses.

GET    /api/conversations        → llista (ordenada per actualitzat_el desc).
GET    /api/conversations/{id}   → conversa + missatges.
DELETE /api/conversations/{id}   → 204.

Cada usuari només veu les seves pròpies converses (aïllament per usuari).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    ConversationDetailResponse,
    ConversationsResponse,
    Conversa,
    Missatge,
)
from app.core.security import Usuari, get_current_user
from app.db.models import Conversation, Message
from app.db.session import get_db

router = APIRouter(prefix="/api/conversations", tags=["converses"])


@router.get("", response_model=ConversationsResponse)
def llista(
    usuari: Usuari = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationsResponse:
    stmt = (
        select(Conversation)
        .where(
            Conversation.usuari == usuari.usuari,
            Conversation.institucio_id == usuari.institucio,
        )
        .order_by(Conversation.actualitzat_el.desc())
    )
    convs = db.scalars(stmt).all()
    sortida = []
    for c in convs:
        n = db.scalar(
            select(func.count(Message.id)).where(Message.conversation_id == c.id)
        )
        sortida.append(
            Conversa(
                id=c.id,
                titol=c.titol,
                agent_id=c.agent_id,
                etiqueta=c.etiqueta,
                actualitzat_el=c.actualitzat_el.isoformat(),
                n_missatges=int(n or 0),
            )
        )
    return ConversationsResponse(conversations=sortida)


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
def detall(
    conversation_id: str,
    usuari: Usuari = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationDetailResponse:
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.usuari != usuari.usuari or conv.institucio_id != usuari.institucio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversa no trobada."
        )
    missatges = db.scalars(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.creat_el)
    ).all()
    return ConversationDetailResponse(
        conversation=Conversa(
            id=conv.id,
            titol=conv.titol,
            agent_id=conv.agent_id,
            etiqueta=conv.etiqueta,
            actualitzat_el=conv.actualitzat_el.isoformat(),
            n_missatges=len(missatges),
        ),
        messages=[
            Missatge(
                id=m.id,
                rol=m.rol,  # type: ignore[arg-type]
                contingut=m.contingut,
                agent_id=m.agent_id,
                fonts=m.fonts,
                confianca=m.confianca,
                creat_el=m.creat_el.isoformat(),
            )
            for m in missatges
        ],
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def esborra(
    conversation_id: str,
    usuari: Usuari = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.usuari != usuari.usuari or conv.institucio_id != usuari.institucio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversa no trobada."
        )
    db.delete(conv)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
