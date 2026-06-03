"""Rate-limit / bloqueig de login en memòria (anti força bruta).

Patró de **bloqueig de compte**: després de N fallits CONSECUTIUS per a una clau
(usuari+institució), es bloqueja durant un temps de refredament. Un login correcte
reseteja el comptador (bona UX: un usuari legítim que s'equivoca un parell de cops i
després encerta NO queda bloquejat).

Implementació en memòria (per procés): suficient per al desplegament actual (un sol
backend). En multi-instància caldria un magatzem compartit (Redis/BD) — vegeu nota a
`docs/14_PROPOSTES_FUNCIONALITATS.md`. Trade-off conegut: el bloqueig per compte permet
un DoS dirigit a un usuari concret; per això el bloqueig és TEMPORAL (no permanent).
"""

from __future__ import annotations

import datetime as dt
import threading

_lock = threading.Lock()
_estat: dict[str, dict] = {}  # clau -> {"fallits": int, "fins": datetime | None}


def _ara() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def segons_bloqueig_restant(clau: str) -> int:
    """Segons que falten de bloqueig per a `clau` (0 si no està bloquejada)."""
    with _lock:
        e = _estat.get(clau)
        if not e or not e.get("fins"):
            return 0
        restant = (e["fins"] - _ara()).total_seconds()
        if restant <= 0:
            # Expirat: neteja per permetre tornar a intentar-ho.
            _estat.pop(clau, None)
            return 0
        return int(restant) + 1


def registra_fallit(clau: str, max_intents: int, bloqueig_segons: int) -> None:
    """Comptabilitza un intent fallit; bloqueja la clau si arriba al màxim."""
    with _lock:
        e = _estat.setdefault(clau, {"fallits": 0, "fins": None})
        e["fallits"] += 1
        if e["fallits"] >= max_intents:
            e["fins"] = _ara() + dt.timedelta(seconds=bloqueig_segons)


def registra_exit(clau: str) -> None:
    """Login correcte → reseteja el comptador de la clau."""
    with _lock:
        _estat.pop(clau, None)


def reinicia() -> None:
    """Buida tot l'estat (per a tests)."""
    with _lock:
        _estat.clear()
