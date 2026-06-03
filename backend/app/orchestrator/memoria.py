"""Memòria conversacional: gestió de converses i missatges a la BD.

Encapsula la persistència de converses perquè els routers i l'orquestrador no
toquin l'ORM directament. Una conversa es crea si `conversation_id` és None.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.registry import get_agent
from app.db.models import Conversation, Message


def _titol_des_de(message: str) -> str:
    """Deriva un títol curt per a una conversa nova a partir del primer missatge."""
    net = message.strip().replace("\n", " ")
    return (net[:60] + "…") if len(net) > 60 else net or "Nova conversa"


def obte_o_crea_conversa(
    db: Session,
    conversation_id: str | None,
    agent_id: str,
    usuari: str,
    rol: str,
    primer_missatge: str,
    institucio: str = "nou_patufet",
) -> Conversation:
    """Recupera una conversa existent o en crea una de nova."""
    if conversation_id:
        conv = db.get(Conversation, conversation_id)
        if conv is not None:
            return conv

    agent = get_agent(agent_id)
    conv = Conversation(
        id=conversation_id or None,  # deixa que el default generi l'id si és None
        titol=_titol_des_de(primer_missatge),
        agent_id=agent_id,
        etiqueta=(agent.nom if agent else None),
        usuari=usuari,
        rol=rol,
        institucio_id=institucio,
    )
    db.add(conv)
    db.flush()
    return conv


def historial(db: Session, conversation_id: str, limit: int = 12) -> list[dict[str, str]]:
    """Retorna l'historial de missatges en format de chat (role/content)."""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.creat_el)
        .limit(limit)
    )
    missatges = db.scalars(stmt).all()
    return [{"role": m.rol, "content": m.contingut} for m in missatges]


def afegeix_missatge(
    db: Session,
    conversation_id: str,
    rol: str,
    contingut: str,
    *,
    agent_id: str | None = None,
    fonts: list[dict] | None = None,
    confianca: float | None = None,
) -> Message:
    """Persisteix un missatge i actualitza la marca de temps de la conversa."""
    msg = Message(
        conversation_id=conversation_id,
        rol=rol,
        contingut=contingut,
        agent_id=agent_id,
        fonts=fonts,
        confianca=confianca,
    )
    db.add(msg)
    conv = db.get(Conversation, conversation_id)
    if conv is not None:
        conv.actualitzat_el = dt.datetime.now(dt.timezone.utc)
    db.commit()
    db.refresh(msg)
    return msg
