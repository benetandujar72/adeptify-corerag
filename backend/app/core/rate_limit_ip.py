"""Rate-limit per IP per al canal públic (en memòria, per procés).

Defensa bàsica contra abús del canal públic (`/api/public/*`). Per a producció
amb múltiples instàncies del backend, substituir per Redis o equivalent
(magatzem compartit) — l'API d'aquest mòdul es manté igual.
"""

from __future__ import annotations

import threading
import time

# Estat: ip → (finestra_inici_ts, comptador).
_finestra_seg = 60.0
_state: dict[str, tuple[float, int]] = {}
_lock = threading.Lock()


def consumeix(ip: str, max_per_minut: int) -> tuple[bool, int]:
    """Retorna (permès, segons fins al reset).

    Implementació senzilla de finestra fixa per minut: en començar la primera
    petició s'inicia la finestra; quan caduca, es reseteja. Suficient per al
    rate-limit del widget de xat.
    """
    if not ip or max_per_minut <= 0:
        return (True, 0)
    ara = time.monotonic()
    with _lock:
        inici, n = _state.get(ip, (ara, 0))
        if ara - inici >= _finestra_seg:
            inici = ara
            n = 0
        n += 1
        _state[ip] = (inici, n)
        if n > max_per_minut:
            return (False, int(_finestra_seg - (ara - inici)) + 1)
    return (True, 0)


def reinicia() -> None:
    """Reseteja tot l'estat (tests)."""
    with _lock:
        _state.clear()
