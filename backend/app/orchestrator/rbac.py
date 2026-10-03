"""Permisos d'agents i documents: rol i centre verificats al servidor."""

from __future__ import annotations

from fastapi import HTTPException, status

from app.agents.registry import AgentDef, get_agent
from app.core.roles import Rol


def comprova_acces_agent(
    agent_id: str, rol: Rol, agents: dict | None = None
) -> AgentDef:
    """Retorna l'agent si el rol hi té accés; si no, llança 403/404.

    - 404 si l'agent no existeix.
    - 403 si l'agent existeix però el rol no hi està permès.
    `agents` = mapa institution-aware (built-ins + personalitzats); per defecte built-ins.
    """
    agent = get_agent(agent_id, agents)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent desconegut: {agent_id}",
        )
    # El superadmin (god mode) té accés a tots els agents.
    if rol != Rol.SUPERADMIN and rol not in agent.rols_permesos:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"El rol '{rol.value}' no té accés a l'agent '{agent.nom}'."
            ),
        )
    return agent


def doc_ids_permesos(
    rol: Rol, db=None, institucio_id: str | None = None
) -> set[str]:
    """Permisos documentals calculats al servidor i confinats al centre.

    Sense context verificable no es concedeix cap document. Famílies i alumnat
    només reben coneixement classificat públic explícitament; sensible o
    desconegut mai entra al RAG, tampoc per a administració.
    """
    if db is None or not institucio_id or not isinstance(rol, Rol):
        return set()
    from sqlalchemy import select
    from app.db.models import Document

    stmt = select(Document.doc_id).where(
        Document.institucio_id == institucio_id,
        Document.sensibilitat.in_(("public", "docent", "intern")),
    )
    if rol in {Rol.FAMILIA, Rol.ALUMNE}:
        stmt = stmt.where(Document.sensibilitat == "public", Document.visibilitat == "tots")
    elif rol not in {Rol.DIRECCIO, Rol.PAS, Rol.SUPERADMIN}:
        stmt = stmt.where(Document.visibilitat == "tots")
    return set(db.scalars(stmt).all())
