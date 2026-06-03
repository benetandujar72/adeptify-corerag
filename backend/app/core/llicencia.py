"""Capa de negoci: llicències, plans i features per institució.

Model de comercialització: **instància dedicada per centre**. Cada centre té el
seu desplegament; la **llicència** determina QUINS mòduls (features) estan actius
i quins LÍMITS d'ús té (nombre d'usuaris, alumnes, documents). No és facturació
per ús (SaaS): és llicenciament per capacitats, verificat localment.

La llicència es desa a `Institucio.config["llicencia"]`:
    {
        "pla": "essencial" | "avancat" | "enterprise",
        "features": ["matricula", "avaluacio", ...],   # opcional; si falta → les del pla
        "limits": {"max_usuaris": 50, "max_alumnes": 500, "max_documents": 1000},
        "data_inici": "2026-09-01",
        "data_caducitat": "2027-08-31",   # opcional; None = perpètua
        "estat": "activa" | "prova" | "suspesa"   # opcional; es deriva de les dates
    }

RETROCOMPATIBILITAT (clau): si una institució NO té llicència definida, es
considera **enterprise amb tot actiu i sense límits**. Així el desplegament
actual (nou_patufet) i tots els tests existents continuen funcionant sense canvis.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

# ── Catàleg de features (mòduls activables per llicència) ──────────────────
# La clau és l'identificador intern; el valor és l'etiqueta humana per a la UI.
FEATURES: dict[str, str] = {
    "xat": "Assistents de xat (RAG)",
    "documents": "Gestió documental",
    "skills": "Estudi d'Skills (agents propis)",
    "matricula": "Matrícula",
    "assistencia": "Assistència i absentisme",
    "avaluacio": "Avaluació LOMLOE",
    "pagaments": "Pagaments i quotes",
    "tasques": "Tasques i recordatoris",
    "importacio": "Importació massiva",
    "expedients": "Expedients",
    "recursos": "Documentació i recursos",
    "correu": "Seguiment de correu",
    "registre_es": "Registre d'entrada/sortida de documents",
    "certificats": "Generador de certificats oficials",
    "comunicacions": "Circulars i comunicacions a famílies",
    "agenda": "Agenda del centre i venciments normatius",
    "telegram": "Canal Telegram",
    "public": "Canal públic (web/WordPress)",
    "integracions": "Integracions externes (Google/Clickedu…)",
}

# ── Plans comercials ────────────────────────────────────────────────────────
# Cada pla defineix les features incloses i els límits per defecte.
# 'enterprise' = totes les features, sense límits.
PLANS: dict[str, dict[str, Any]] = {
    "essencial": {
        "nom": "Essencial",
        "descripcio": "Xat IA amb RAG, gestió documental i tasques. Per a centres que comencen.",
        "features": ["xat", "documents", "tasques", "recursos"],
        "limits": {"max_usuaris": 25, "max_alumnes": 0, "max_documents": 300},
    },
    "avancat": {
        "nom": "Avançat",
        "descripcio": "Gestió escolar completa LOMLOE + skills propis. El pla recomanat.",
        "features": [
            "xat", "documents", "skills", "matricula", "assistencia",
            "avaluacio", "pagaments", "tasques", "importacio", "expedients",
            "recursos", "correu", "registre_es", "certificats", "comunicacions", "agenda",
        ],
        "limits": {"max_usuaris": 150, "max_alumnes": 1000, "max_documents": 2000},
    },
    "enterprise": {
        "nom": "Enterprise",
        "descripcio": "Tot inclòs, sense límits, multicanal (Telegram, web pública, integracions).",
        "features": list(FEATURES.keys()),
        "limits": {"max_usuaris": 0, "max_alumnes": 0, "max_documents": 0},  # 0 = il·limitat
    },
}

# Pla per defecte quan no hi ha llicència definida (retrocompatibilitat total).
PLA_DEFECTE = "enterprise"


def _avui() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


def _parse_data(s: str | None) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def llegeix(config: dict | None) -> dict[str, Any]:
    """Normalitza la llicència d'una institució. Sense llicència → enterprise/tot actiu."""
    secc = (config or {}).get("llicencia") or {}
    pla = secc.get("pla")
    if pla not in PLANS:
        pla = PLA_DEFECTE
    base = PLANS[pla]
    # Features: explícites si n'hi ha; si no, les del pla. Sempre filtrades al catàleg.
    feats = secc.get("features")
    if not isinstance(feats, list):
        feats = base["features"]
    features = [f for f in feats if f in FEATURES]
    # Límits: els del pla, sobreescrits pels explícits.
    limits = dict(base["limits"])
    for k, v in (secc.get("limits") or {}).items():
        if isinstance(v, int):
            limits[k] = v
    data_inici = secc.get("data_inici")
    data_caducitat = secc.get("data_caducitat")
    estat = _estat(secc)
    return {
        "pla": pla,
        "pla_nom": base["nom"],
        "features": features,
        "limits": limits,
        "data_inici": data_inici,
        "data_caducitat": data_caducitat,
        "estat": estat,
        "dies_fins_caducitat": _dies_fins(data_caducitat),
    }


def _estat(secc: dict[str, Any]) -> str:
    """Deriva l'estat: suspesa (manual) > caducada (data) > prova/activa."""
    if secc.get("estat") == "suspesa":
        return "suspesa"
    cad = _parse_data(secc.get("data_caducitat"))
    if cad is not None and cad < _avui():
        return "caducada"
    if secc.get("estat") == "prova":
        return "prova"
    return "activa"


def _dies_fins(data_caducitat: str | None) -> int | None:
    cad = _parse_data(data_caducitat)
    if cad is None:
        return None
    return (cad - _avui()).days


def feature_activa(config: dict | None, feature: str) -> bool:
    """Cert si la feature està inclosa a la llicència I la llicència no està
    suspesa/caducada. Sense llicència → True (enterprise per defecte)."""
    lic = llegeix(config)
    if lic["estat"] in ("suspesa", "caducada"):
        return False
    return feature in lic["features"]


def limit(config: dict | None, clau: str) -> int:
    """Retorna el límit (0 = il·limitat). Sense llicència → 0 (il·limitat)."""
    return int(llegeix(config)["limits"].get(clau, 0) or 0)


def dins_de_limit(config: dict | None, clau: str, us_actual: int) -> bool:
    """Cert si encara es pot afegir un element més (us_actual < límit). 0 = il·limitat."""
    lim = limit(config, clau)
    if lim <= 0:
        return True
    return us_actual < lim


def fusiona(
    config: dict | None,
    *,
    pla: str | None = None,
    features: list[str] | None = None,
    limits: dict[str, int] | None = None,
    data_inici: str | None = None,
    data_caducitat: str | None = None,
    estat: str | None = None,
) -> dict[str, Any]:
    """Aplica canvis a `Institucio.config['llicencia']` i retorna una còpia nova."""
    nou = dict(config or {})
    secc = dict(nou.get("llicencia") or {})
    if pla is not None and pla in PLANS:
        secc["pla"] = pla
    if features is not None:
        secc["features"] = [f for f in features if f in FEATURES]
    if limits is not None:
        secc["limits"] = {k: int(v) for k, v in limits.items() if isinstance(v, (int, float))}
    if data_inici is not None:
        secc["data_inici"] = data_inici
    if data_caducitat is not None:
        secc["data_caducitat"] = data_caducitat
    if estat is not None and estat in ("activa", "prova", "suspesa"):
        secc["estat"] = estat
    nou["llicencia"] = secc
    return nou


def cataleg_plans() -> list[dict[str, Any]]:
    """Catàleg de plans per a la UI (operador)."""
    return [
        {
            "id": pid,
            "nom": p["nom"],
            "descripcio": p["descripcio"],
            "features": p["features"],
            "limits": p["limits"],
        }
        for pid, p in PLANS.items()
    ]
