"""Telemetria de privadesa: comptador de crides a APIs comercials de tercers.

El principi rector del projecte és «cap crida a APIs comercials de tercers»
(OpenAI/Anthropic/Gemini). Aquest comptador ha de romandre SEMPRE a 0 i es
reporta a `/api/system/status` (camp `privadesa.crides_externes`).

Tota inferència passa per un endpoint OpenAI-compatible auto-allotjat
(`OPENAI_BASE_URL`). Si mai algú intentés cridar un domini de tercers, el
client LLM hauria de bloquejar-ho i incrementar aquest comptador, deixant
constància de l'incident.
"""

from __future__ import annotations

import threading

# Dominis de proveïdors comercials que MAI s'han de contactar.
DOMINIS_PROHIBITS: frozenset[str] = frozenset(
    {
        "api.openai.com",
        "api.anthropic.com",
        "generativelanguage.googleapis.com",
        "api.cohere.ai",
        "api.mistral.ai",
    }
)

_lock = threading.Lock()
_crides_externes = 0
# Crides a INTEGRACIONS (Google Drive/Gmail/Calendar). NO són inferència LLM:
# es comptabilitzen a part i amb transparència; NO contaminen `crides_externes`.
_crides_integracions = 0


def registra_crida_externa(domini: str) -> None:
    """Incrementa el comptador de crides externes (només per a incidents)."""
    global _crides_externes
    with _lock:
        _crides_externes += 1


def crides_externes() -> int:
    """Retorna el nombre de crides a APIs de tercers (ha de ser 0)."""
    with _lock:
        return _crides_externes


def registra_crida_integracio(connector: str) -> None:
    """Incrementa el comptador de crides a integracions externes (Drive/Gmail…)."""
    global _crides_integracions
    with _lock:
        _crides_integracions += 1


def crides_integracions() -> int:
    """Retorna el nombre de crides a integracions externes (≠ inferència)."""
    with _lock:
        return _crides_integracions


def reinicia() -> None:
    """Reinicia els comptadors (útil en tests)."""
    global _crides_externes, _crides_integracions
    with _lock:
        _crides_externes = 0
        _crides_integracions = 0


def es_domini_prohibit(base_url: str) -> bool:
    """Comprova si una URL base apunta a un proveïdor comercial prohibit."""
    base = base_url.lower()
    return any(domini in base for domini in DOMINIS_PROHIBITS)
