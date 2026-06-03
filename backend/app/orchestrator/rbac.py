"""RBAC: comprovacions d'accés a agents (i, en el futur, a documents per rol).

Al MVP tots els documents indexats són del centre i accessibles per als rols
interns; el filtratge fi per document es deixa preparat (`doc_ids_permesos`)
però retorna None (sense restricció) per defecte. L'accés als AGENTS sí que es
filtra estrictament pel rol.
"""

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


def doc_ids_permesos(rol: Rol) -> set[str] | None:
    """Conjunt de doc_ids accessibles per al rol, o None si no hi ha restricció.

    Ganxo per a un control documental més fi en el futur (p. ex. amagar actes de
    direcció a les famílies). Al MVP retorna None (tots els documents indexats).
    """
    return None
