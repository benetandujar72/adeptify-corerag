"""Endpoint de xat (cor del sistema): POST /api/chat.

- stream=false → ChatResponse JSON amb el Message final, fonts i confiança.
- stream=true  → Server-Sent Events amb esdeveniments token, sources, done, error.

Tota petició queda al registre d'auditoria (usuari, agent, fonts, conversation_id).
"""

from __future__ import annotations

import datetime as dt
import json
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.api.schemas import ChatRequest, ChatResponse, Font, Missatge
from app.core import audit
from app.core.security import Usuari, get_current_user
from app.db.session import get_db
from app.orchestrator import memoria
from app.orchestrator.graph import ResultatOrquestracio, get_orchestrator
from app.orchestrator.recursos import suggereix_recursos

router = APIRouter(prefix="/api", tags=["xat"])


def _confianca(prep: ResultatOrquestracio) -> float:
    """Confiança agregada a partir dels scores de rerank (0..1)."""
    if not prep.resultats:
        return 0.0
    millor = max(r.score for r in prep.resultats)
    return round(float(millor), 2)


def _prepara(db: Session, usuari: Usuari, cos: ChatRequest):
    """Part comuna: crea/recupera conversa, prepara orquestració i historial."""
    conv = memoria.obte_o_crea_conversa(
        db,
        cos.conversation_id,
        cos.agent_id,
        usuari.usuari,
        usuari.rol.value,
        cos.message,
        institucio=usuari.institucio,
    )
    db.commit()
    hist = memoria.historial(db, conv.id)
    # Desa el missatge de l'usuari.
    memoria.afegeix_missatge(db, conv.id, "user", cos.message)

    orq = get_orchestrator(db)
    prep = orq.prepara(
        cos.message, cos.agent_id, usuari.rol, hist,
        institucio=usuari.institucio, usuari_nom=usuari.usuari,
    )
    return conv, orq, prep


@router.post("/chat")
def chat(
    cos: ChatRequest,
    usuari: Usuari = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Gestiona una consulta de xat (streaming o no)."""
    conv, orq, prep = _prepara(db, usuari, cos)
    fonts: list[Font] = prep.fonts
    confianca = _confianca(prep)
    # Recursos de documentació VERIFICATS que el sistema suggereix per tema (F2).
    # No provenen de l'LLM: surten del registre curat de la institució.
    recursos = suggereix_recursos(db, usuari.institucio, cos.message, usuari.rol)

    if not cos.stream:
        text = orq.genera(prep)
        msg = memoria.afegeix_missatge(
            db,
            conv.id,
            "assistant",
            text,
            agent_id=prep.agent_id,
            fonts=[f.model_dump() for f in fonts],
            confianca=confianca,
        )
        audit.registra_chat(
            db,
            usuari=usuari.usuari,
            rol=usuari.rol.value,
            agent_utilitzat=prep.agent_id,
            conversation_id=conv.id,
            fonts=[f.model_dump() for f in fonts],
            message_id=msg.id,
            intencio=prep.intencio,
            model_utilitzat=prep.model_utilitzat,
        )
        return ChatResponse(
            conversation_id=conv.id,
            message=Missatge(
                id=msg.id,
                rol="assistant",
                contingut=text,
                agent_id=prep.agent_id,
                fonts=fonts,
                confianca=confianca,
                creat_el=msg.creat_el.isoformat(),
                proposta=prep.proposta,
            ),
            agent_utilitzat=prep.agent_id,
            recursos_suggerits=recursos,
        )

    # ── Streaming SSE ────────────────────────────────────────────────────────
    def generador():
        # Esdeveniment inicial amb les fonts (retrieval ja fet).
        yield {
            "event": "sources",
            "data": json.dumps([f.model_dump() for f in fonts], ensure_ascii=False),
        }
        # Recursos de documentació suggerits (verificats, del registre curat).
        yield {
            "event": "recursos",
            "data": json.dumps([r.model_dump() for r in recursos], ensure_ascii=False),
        }
        trossos: list[str] = []
        try:
            for delta in orq.genera_stream(prep):
                trossos.append(delta)
                yield {"event": "token", "data": delta}
        except Exception:  # noqa: BLE001
            # No exposem mai el detall de l'excepció al client (pot contenir
            # dades sensibles o interns); el registrem al servidor per a auditoria.
            logging.getLogger(__name__).exception("Error generant la resposta de xat (stream)")
            yield {
                "event": "error",
                "data": json.dumps(
                    {"codi": "INTERNAL", "missatge": "Error intern generant la resposta."},
                    ensure_ascii=False,
                ),
            }
            return

        text = "".join(trossos)
        msg = memoria.afegeix_missatge(
            db,
            conv.id,
            "assistant",
            text,
            agent_id=prep.agent_id,
            fonts=[f.model_dump() for f in fonts],
            confianca=confianca,
        )
        audit.registra_chat(
            db,
            usuari=usuari.usuari,
            rol=usuari.rol.value,
            agent_utilitzat=prep.agent_id,
            conversation_id=conv.id,
            fonts=[f.model_dump() for f in fonts],
            message_id=msg.id,
            intencio=prep.intencio,
            model_utilitzat=prep.model_utilitzat,
        )
        message_final = Missatge(
            id=msg.id,
            rol="assistant",
            contingut=text,
            agent_id=prep.agent_id,
            fonts=fonts,
            confianca=confianca,
            creat_el=msg.creat_el.isoformat(),
            proposta=prep.proposta,
        )
        yield {
            "event": "done",
            "data": json.dumps(
                {
                    "conversation_id": conv.id,
                    "message": message_final.model_dump(),
                    "agent_utilitzat": prep.agent_id,
                },
                ensure_ascii=False,
            ),
        }

    return EventSourceResponse(generador())
