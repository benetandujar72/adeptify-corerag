"""Servei intern del nucli (suite → core): generació de PROPOSTES pedagògiques.

Prefix `/api/servei` (autenticat amb CORE_SERVICE_TOKEN, vegeu `servei_auth`).

Aquest endpoint és el punt de delegació de la inferència del suite (privat,
comercial) cap al nucli (públic, AGPL). El nucli és el MOTOR pedagògic genèric:
rep unes instruccions, uns criteris d'avaluació de referència i (opcionalment) una
evidència textual, i retorna una proposta generada amb un model auto-allotjat.

Frontera open-core (innegociable):
- El nucli NO coneix el domini escolar ni desa res: no hi ha alumnes, notes ni
  PII. Tot el context (criteris LOMLOE, text de l'evidència) l'aporta el cridador.
- La proposta és això, una PROPOSTA: el suite la desa com a no validada i un humà
  la valida (supervisió art. 14 AI Act). Marquem sempre `assistit_per_ia=True`.
- Inferència 100% local (Ollama/vLLM): `crides_externes` es manté a 0.
"""

from __future__ import annotations

import json
import logging
import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.agents.registry import get_agent
from app.core.config import Settings, get_settings
from app.core.servei_auth import verifica_servei
from app.rag.llm import get_llm_client

logger = logging.getLogger("adeptify.servei")

router = APIRouter(prefix="/api/servei", tags=["servei"])

# Personas pedagògiques que el servei pot adoptar. Excloem els agents de
# tool-calling (assistent_admin, seguiment_correu): aquí només generem text.
_PERSONES_PERMESES = frozenset(
    {
        "avaluacions",
        "copilot_rubriques",
        "copilot_didactic",
        "copilot_context",
        "copilot_contingut",
        "copilot_format",
        "copilot_exercicis",
        "copilot_adaptacions",
        "copilot_seguiment",
        "copilot_butlleti",
        "copilot_qualitat",
        "tutor_mates",
        "documental",
    }
)

_SISTEMA_GENERIC = (
    "Ets un assistent pedagògic expert en el marc competencial LOMLOE. Ajudes "
    "el professorat a dissenyar i valorar materials i evidències d'aprenentatge. "
    "Escrius en català correcte i normatiu (IEC), sense castellanismes."
)

_GUARDA = (
    "\n\nNORMES: proposes, no decideixes (un docent validarà la teva proposta). "
    "Fonamenta't NOMÉS en els criteris i l'evidència aportats; no inventis dades "
    "d'alumnes ni continguts aliens. Si manca informació, fes-ho explícit."
)

_REFORC_JSON = (
    "\n\nRespon EXCLUSIVAMENT amb un objecte JSON vàlid, sense text addicional ni "
    "blocs de codi."
)


class PropostaServeiRequest(BaseModel):
    """Petició de proposta pedagògica (el suite aporta tot el context)."""

    instruccions: str = Field(..., min_length=1, max_length=6000)
    agent_id: str | None = Field(default=None, max_length=64)
    sistema: str | None = Field(default=None, max_length=4000)
    criteris: list[str] = Field(default_factory=list, max_length=200)
    evidencia: str | None = Field(default=None, max_length=8000)
    format_json: bool = False
    catala: bool = True
    temperatura: float = Field(default=0.3, ge=0.0, le=1.0)


class PropostaServeiResponse(BaseModel):
    """Proposta generada. `proposta_json` només si s'ha demanat `format_json`."""

    proposta: str
    proposta_json: dict | None = None
    agent_id: str | None = None
    model: str
    assistit_per_ia: bool = True


def _extreu_json(text: str) -> dict | None:
    """Primer objecte JSON d'un text (tolera fences markdown i soroll)."""
    if not text:
        return None
    net = text.strip()
    if net.startswith("```"):
        net = re.sub(r"^```[a-zA-Z]*\n?", "", net)
        net = re.sub(r"\n?```$", "", net).strip()
    try:
        dades = json.loads(net)
        return dades if isinstance(dades, dict) else None
    except (ValueError, TypeError):
        pass
    m = re.search(r"\{.*\}", net, flags=re.DOTALL)
    if m:
        try:
            dades = json.loads(m.group(0))
            return dades if isinstance(dades, dict) else None
        except (ValueError, TypeError):
            return None
    return None


def _munta_messages(cos: PropostaServeiRequest) -> list[dict[str, str]]:
    # Persona: si s'indica un agent permès, fem servir el seu system prompt.
    sistema: str | None = None
    if cos.agent_id and cos.agent_id in _PERSONES_PERMESES:
        agent = get_agent(cos.agent_id)
        if agent is not None:
            sistema = agent.system_prompt
    # Si el cridador aporta el seu propi system complet, té prioritat (s'hi afegeix,
    # o el substitueix si no hi ha persona) → el suite conserva el seu contracte exacte.
    if cos.sistema:
        sistema = f"{sistema}\n\n{cos.sistema.strip()}" if sistema else cos.sistema.strip()
    if not sistema:
        sistema = _SISTEMA_GENERIC
    sistema += _GUARDA
    if cos.format_json:
        sistema += _REFORC_JSON

    parts = [cos.instruccions.strip()]
    if cos.criteris:
        linies = "\n".join(f"- {c.strip()}" for c in cos.criteris if c and c.strip())
        if linies:
            parts.append("Criteris d'avaluació de referència del centre:\n" + linies)
    if cos.evidencia and cos.evidencia.strip():
        parts.append("Evidència / resposta a valorar:\n«" + cos.evidencia.strip() + "»")
    usuari = "\n\n".join(parts)
    return [
        {"role": "system", "content": sistema},
        {"role": "user", "content": usuari},
    ]


@router.post("/proposta", response_model=PropostaServeiResponse)
def proposta(
    cos: PropostaServeiRequest,
    _cridador: str = Depends(verifica_servei),
    settings: Settings = Depends(get_settings),
) -> PropostaServeiResponse:
    """Genera una proposta pedagògica a partir del context aportat pel suite.

    Stateless: no desa res ni rep PII estructurada (només text d'evidència). La
    inferència és local (Ollama/vLLM); no contamina `crides_externes`.
    """
    messages = _munta_messages(cos)
    client = get_llm_client()
    text = client.complete(messages, catala=cos.catala, temperatura=cos.temperatura)
    model = settings.llm_model_catala if cos.catala else settings.llm_model
    logger.info(
        "servei.proposta agent=%s json=%s criteris=%d evidencia=%s",
        cos.agent_id or "—",
        cos.format_json,
        len(cos.criteris),
        bool(cos.evidencia),
    )
    return PropostaServeiResponse(
        proposta=text,
        proposta_json=_extreu_json(text) if cos.format_json else None,
        agent_id=cos.agent_id,
        model=model,
    )
