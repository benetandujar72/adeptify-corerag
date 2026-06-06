"""Exportacio assistida ARSUL en mode segur.

El modul prepara un paquet JSON per exercir drets RGPD d'acces/portabilitat
sense modificar dades. No exporta secrets d'autenticacio i evita filtrar
auditoria entre institucions quan hi ha usernames duplicats.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, Conversation, Feedback, Message, TelegramBinding, User


def _iso(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value else None


def _profile(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "rol": user.rol,
        "institucio_id": user.institucio_id,
        "nom": user.nom,
        "email": user.email,
        "actiu": user.actiu,
        "mfa_actiu": bool(user.totp_actiu),
        "idioma": user.idioma,
        "creat_el": _iso(user.creat_el),
        "ultim_acces": _iso(user.ultim_acces),
    }


def _message(row: Message) -> dict[str, Any]:
    return {
        "id": row.id,
        "rol": row.rol,
        "contingut": row.contingut,
        "agent_id": row.agent_id,
        "fonts": row.fonts,
        "confianca": row.confianca,
        "creat_el": _iso(row.creat_el),
    }


def _conversation(row: Conversation, messages: list[Message]) -> dict[str, Any]:
    return {
        "id": row.id,
        "titol": row.titol,
        "agent_id": row.agent_id,
        "etiqueta": row.etiqueta,
        "institucio_id": row.institucio_id,
        "usuari": row.usuari,
        "rol": row.rol,
        "creat_el": _iso(row.creat_el),
        "actualitzat_el": _iso(row.actualitzat_el),
        "messages": [_message(m) for m in messages],
    }


def _feedback(row: Feedback) -> dict[str, Any]:
    return {
        "id": row.id,
        "message_id": row.message_id,
        "valor": row.valor,
        "comentari": row.comentari,
        "usuari": row.usuari,
        "institucio_id": row.institucio_id,
        "creat_el": _iso(row.creat_el),
    }


def _telegram(row: TelegramBinding) -> dict[str, Any]:
    return {
        "chat_id": row.chat_id,
        "usuari": row.usuari,
        "institucio_id": row.institucio_id,
        "rol": row.rol,
        "actiu": row.actiu,
        "creat_el": _iso(row.creat_el),
    }


def _audit(row: AuditLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "usuari": row.usuari,
        "rol": row.rol,
        "accio": row.accio,
        "agent": row.agent,
        "conversation_id": row.conversation_id,
        "detalls": row.detalls,
        "creat_el": _iso(row.creat_el),
    }


def build_export(db: Session, *, username: str, institucio_id: str) -> dict[str, Any]:
    """Retorna un paquet ARSUL per a `username` dins d'una institucio.

    L'auditoria historica no te `institucio_id`. Si el mateix username existeix
    en mes d'un centre, nomes exportem registres auditables vinculats a les
    converses del centre per evitar una fuga cross-tenant.
    """

    user = db.scalar(
        select(User).where(User.username == username, User.institucio_id == institucio_id)
    )
    if user is None:
        raise LookupError("usuari_no_trobat")

    duplicated_username = int(
        len(db.scalars(select(User.id).where(User.username == username)).all())
    ) > 1

    conversations = list(
        db.scalars(
            select(Conversation)
            .where(Conversation.usuari == username, Conversation.institucio_id == institucio_id)
            .order_by(Conversation.creat_el.asc())
        ).all()
    )
    conv_ids = [c.id for c in conversations]
    messages_by_conv: dict[str, list[Message]] = defaultdict(list)
    if conv_ids:
        for row in db.scalars(
            select(Message)
            .where(Message.conversation_id.in_(conv_ids))
            .order_by(Message.creat_el.asc())
        ).all():
            messages_by_conv[row.conversation_id].append(row)

    feedback = list(
        db.scalars(
            select(Feedback)
            .where(Feedback.usuari == username, Feedback.institucio_id == institucio_id)
            .order_by(Feedback.creat_el.asc())
        ).all()
    )
    telegram = list(
        db.scalars(
            select(TelegramBinding)
            .where(
                TelegramBinding.usuari == username,
                TelegramBinding.institucio_id == institucio_id,
            )
            .order_by(TelegramBinding.creat_el.asc())
        ).all()
    )

    limitacions: list[str] = []
    audit_stmt = select(AuditLog).where(AuditLog.usuari == username)
    if duplicated_username:
        limitacions.append(
            "audit_log_no_te_institucio_id: amb username duplicat, nomes s'inclou "
            "l'auditoria vinculada a converses d'aquest centre."
        )
        audit_stmt = audit_stmt.where(AuditLog.conversation_id.in_(conv_ids)) if conv_ids else None
    if audit_stmt is None:
        audit_rows: list[AuditLog] = []
    else:
        audit_rows = list(db.scalars(audit_stmt.order_by(AuditLog.creat_el.asc())).all())

    paquet = {
        "mode": "export",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "subject": {"username": username, "institucio_id": institucio_id},
        "scope": [
            "perfil_usuari",
            "converses",
            "missatges",
            "feedback",
            "telegram_bindings",
            "audit_log",
        ],
        "profile": _profile(user),
        "conversations": [
            _conversation(c, messages_by_conv.get(c.id, [])) for c in conversations
        ],
        "feedback": [_feedback(f) for f in feedback],
        "telegram_bindings": [_telegram(t) for t in telegram],
        "audit_log": [_audit(a) for a in audit_rows],
        "limitacions": limitacions,
    }
    paquet["summary"] = {
        "converses": len(paquet["conversations"]),
        "missatges": sum(len(c["messages"]) for c in paquet["conversations"]),
        "feedback": len(paquet["feedback"]),
        "telegram_bindings": len(paquet["telegram_bindings"]),
        "audit_log": len(paquet["audit_log"]),
    }
    return paquet
