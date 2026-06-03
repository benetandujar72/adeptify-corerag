"""Els 4 agents especialitzats (mockup 02)."""

from app.agents.registry import (
    AGENTS,
    AgentDef,
    agents_per_rol,
    get_agent,
    llista_agents,
)

__all__ = [
    "AGENTS",
    "AgentDef",
    "agents_per_rol",
    "get_agent",
    "llista_agents",
]
