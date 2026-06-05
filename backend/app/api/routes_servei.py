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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agents.registry import get_agent
from app.core.config import Settings, get_settings
from app.core.guardrails import (
    SECURITY_SYSTEM_PROMPT,
    detect_injection,
    sanitize_result,
    wrap_untrusted,
)
from app.core.principis import AVIS_PROPOSTA, GUARDRAIL_HUMANISME
from app.core.servei_auth import verifica_servei
from app.rag.llm import get_llm_client

# Llindar de rebuig al CANAL D'INSTRUCCIÓ: exigim ≥2 senyals d'injecció distints
# per rebutjar (no 1), perquè en un domini d'avaluació una sola paraula com
# «ignora» o «instruccions» apareix legítimament (p. ex. «valora si l'alumne
# ignora les instruccions de l'exercici»). Dos senyals junts ja són un atac clar.
_LLINDAR_INSTRUCCIO = 2

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
    # Avís de transparència (art. 50 AI Act; C/2026/2826): revisió crítica humana.
    avis: str = AVIS_PROPOSTA


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
    # Humanisme digital (Conclusions UE C/2026/2826): el guardrail governa SEMPRE
    # la generació (suport no substitució, transparència crítica de límits/biaixos).
    sistema = f"{GUARDRAIL_HUMANISME}\n\n{sistema}"
    # K5.4 · System prompt de seguretat NO ELIMINABLE, sempre el primer. El
    # cridador només pot AFEGIR (cos.sistema s'annexa), mai treure aquest prefix:
    # garanteix que el model tracti <DATA>…</DATA> com a dada inert i ignori
    # qualsevol ordre d'injecció vinguda del context (defensa estructural).
    sistema = f"{SECURITY_SYSTEM_PROMPT}\n\n{sistema}"
    if cos.format_json:
        sistema += _REFORC_JSON

    parts = [cos.instruccions.strip()]
    # K7.2 · Tot el que no és la INSTRUCCIÓ del cridador és DADA NO FIABLE
    # (criteris del centre, evidència de l'alumnat): s'embolcalla amb <DATA>…</DATA>
    # amb anti-breakout, de manera que cap text d'un document/evidència no pugui
    # reescriure el comportament del model (injecció indirecta).
    if cos.criteris:
        linies = "\n".join(f"- {c.strip()}" for c in cos.criteris if c and c.strip())
        if linies:
            parts.append("Criteris d'avaluació de referència del centre:\n" + wrap_untrusted(linies))
    if cos.evidencia and cos.evidencia.strip():
        parts.append("Evidència / resposta a valorar:\n" + wrap_untrusted(cos.evidencia.strip()))
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

    Defensa contra injecció (K7.1, defensa en profunditat sobre el wrapping <DATA>):
    - CANAL D'INSTRUCCIÓ (instruccions + system del cridador): és el canal que el
      model interpreta com a ordre. Si hi detectem ≥2 senyals d'injecció distints
      (jailbreak clar), REBUTGEM (422) i ho registrem — fail-closed.
    - CANAL DE DADA (criteris + evidència): ja va embolcallat amb <DATA> i el
      system de seguretat l'inertitza; aquí NO rebutgem (l'evidència d'un alumne
      pot contenir legítimament paraules com «ignora»), només ho registrem.
    """
    # ── K7.1 · Screening del canal d'instrucció (fail-closed) ─────────────────
    canal_instruccio = f"{cos.instruccions}\n{cos.sistema or ''}"
    v_instr = detect_injection(canal_instruccio, threshold=_LLINDAR_INSTRUCCIO)
    if v_instr.is_injection:
        logger.warning(
            "servei.proposta REBUTJADA: injecció al canal d'instrucció score=%d matches=%s",
            v_instr.score, ",".join(v_instr.matches),
        )
        raise HTTPException(
            status_code=422,
            detail="La instrucció conté senyals d'injecció de prompt; revisa-la.",
        )
    # ── K7.1 · Monitorització del canal de dada (no rebutja; <DATA> ja l'inertitza)
    canal_dada = "\n".join([*cos.criteris, cos.evidencia or ""])
    v_dada = detect_injection(canal_dada, threshold=1)
    if v_dada.is_injection:
        logger.warning(
            "servei.proposta: senyals d'injecció DINS de <DATA> (neutralitzats) matches=%s",
            ",".join(v_dada.matches),
        )

    messages = _munta_messages(cos)
    client = get_llm_client()
    # K7.4 · Sanititza la sortida del model (NFC, treu zero-width/control, trunca)
    # abans de retornar-la o d'extreure'n JSON.
    text = sanitize_result(
        client.complete(messages, catala=cos.catala, temperatura=cos.temperatura)
    )
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
