"""Classificació d'intenció i selecció d'agent.

L'orquestrador rep l'`agent_id` suggerit pel frontend, però pot reencaminar la
consulta a un altre agent si la intenció hi encaixa millor (API_CONTRACT.md:
«l'orquestrador pot reencaminar»). El routing combina:

1. Una heurística ràpida per paraules clau (sense dependència de cap model),
   suficient i determinista per a tests.
2. Opcionalment, una confirmació via LLM (no usada en tests; el client
   s'embolica).

La detecció de llengua (CA/ES) serveix per a l'agent d'Atenció Famílies.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.registry import AGENTS, AgentDef, get_agent
from app.core.roles import Rol

# Agents dedicats/agèntics: quan el frontend els selecciona explícitament (l'usuari
# és a la seva vista dedicada, p. ex. «Gestió IA» o «Correu»), NO s'han de
# reencaminar a un altre agent encara que el text tingui paraules clau d'un altre
# (allà hi viuen les seves tools/context; reencaminar trencaria el tool-calling).
_AGENTS_FIXOS = {"assistent_admin", "seguiment_correu"}

# Paraules típicament castellanes (heurística lleugera de detecció de llengua).
_MARQUES_ES = {
    "qué", "cómo", "cuándo", "cuánto", "dónde", "horario", "salida", "comedor",
    "niño", "niña", "hijo", "hija", "gracias", "días", "está", "puedo", "quiero",
    "para", "esquí", "reunión", "información",
}


@dataclass
class DecisioRouting:
    """Resultat del routing."""

    agent_id: str
    intencio: str
    reencaminat: bool
    llengua: str  # "ca" | "es"


def detecta_llengua(text: str) -> str:
    """Heurística simple: 'es' si hi ha prou marques castellanes, si no 'ca'."""
    paraules = {p.strip(".,;:!?¿¡()").lower() for p in text.split()}
    if len(paraules & _MARQUES_ES) >= 2:
        return "es"
    return "ca"


def _puntua_agent(agent: AgentDef, text: str) -> int:
    """Compta coincidències de paraules clau de l'agent dins el text."""
    minuscules = text.lower()
    return sum(1 for clau in agent.paraules_clau if clau in minuscules)


def classifica(
    message: str,
    agent_suggerit: str,
    rol: Rol,
    agents: dict[str, AgentDef] | None = None,
) -> DecisioRouting:
    """Decideix quin agent respon i amb quina intenció.

    Regla: es respecta `agent_suggerit` tret que un altre agent (accessible pel
    rol) tingui una puntuació de paraules clau clarament superior. `agents` = mapa
    institution-aware (built-ins + personalitzats); per defecte, només built-ins.
    """
    llengua = detecta_llengua(message)
    font = agents if agents is not None else AGENTS

    suggerit = get_agent(agent_suggerit, agents)
    # Sticky: els agents agèntics fixos I els personalitzats (skills) seleccionats
    # explícitament i accessibles NO es reencaminen (és la vista dedicada de l'usuari).
    es_sticky = agent_suggerit in _AGENTS_FIXOS or agent_suggerit not in AGENTS
    if es_sticky and suggerit is not None and rol in suggerit.rols_permesos:
        return DecisioRouting(
            agent_id=agent_suggerit,
            intencio=_etiqueta_intencio(agent_suggerit),
            reencaminat=False,
            llengua=llengua,
        )
    # Puntuem tots els agents accessibles pel rol.
    puntuacions: dict[str, int] = {}
    for aid, agent in font.items():
        if rol in agent.rols_permesos:
            puntuacions[aid] = _puntua_agent(agent, message)

    # Si el suggerit no és accessible pel rol, hem de triar entre els accessibles.
    millor_id = max(puntuacions, key=lambda k: puntuacions[k]) if puntuacions else agent_suggerit
    millor_score = puntuacions.get(millor_id, 0)
    score_suggerit = puntuacions.get(agent_suggerit, -1)

    suggerit_accessible = suggerit is not None and rol in suggerit.rols_permesos

    if suggerit_accessible and (
        millor_score <= score_suggerit + 1 or score_suggerit < 0
    ):
        # Mantenim el suggerit si és accessible i no hi ha un guanyador molt clar.
        agent_final = agent_suggerit
        reencaminat = False
    else:
        agent_final = millor_id
        reencaminat = agent_final != agent_suggerit

    intencio = _etiqueta_intencio(agent_final)
    return DecisioRouting(
        agent_id=agent_final,
        intencio=intencio,
        reencaminat=reencaminat,
        llengua=llengua,
    )


def _etiqueta_intencio(agent_id: str) -> str:
    """Etiqueta d'intenció llegible per a l'auditoria."""
    return {
        "tutor_mates": "consulta_matematiques",
        "secretaria": "consulta_normativa",
        "families": "atencio_families",
        "documental": "gestio_documental",
        "copilot_didactic": "copilot_didactic",
        "copilot_context": "copilot_context",
        "copilot_contingut": "copilot_contingut",
        "copilot_format": "copilot_format",
        "copilot_exercicis": "copilot_exercicis",
        "copilot_rubriques": "copilot_rubriques",
        "copilot_adaptacions": "copilot_adaptacions",
        "copilot_seguiment": "copilot_seguiment",
        "copilot_butlleti": "copilot_butlleti",
        "copilot_qualitat": "copilot_qualitat",
    }.get(agent_id, "general")
