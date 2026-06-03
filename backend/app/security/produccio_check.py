"""Verificació de l'estat de producció local del centre.

Comprova un conjunt de **controls de seguretat i robustesa** que han d'estar
en ordre quan el sistema fa de servidor real (encara que sigui local) per a
un centre educatiu. Cada control retorna una severitat:

- `ok`     → tot correcte
- `info`   → ajust raonable per dev; recomanat endurir en producció
- `avis`   → toca arreglar abans d'usar amb dades reals de menors
- `critic` → seguretat compromesa; cal acció immediata

NO és destructiu: només llegeix l'estat. La direcció/superadmin el pot
consultar via `/api/system/produccio` o executant `python -m scripts.produccio_check`.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import socket
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.db.models import AuditLog, Institucio, User
from app.db.session import get_sessionmaker

Severitat = str  # "ok" | "info" | "avis" | "critic"
_ORDRE = {"ok": 0, "info": 1, "avis": 2, "critic": 3}


@dataclass(frozen=True)
class Control:
    clau: str
    titol: str
    severitat: Severitat
    detall: str
    recomanacio: str | None = None


# ─────────────────────────── Controls ──────────────────────────────


def _feble(valor: str) -> bool:
    """Heurística: el secret conté patrons clarament de dev."""
    v = (valor or "").lower()
    return any(p in v for p in ("test", "dev", "demo", "secret-de", "changeme",
                                "canviar", "default", "exemple"))


def _control_entorn(s: Settings) -> Control:
    e = (s.entorn or "").lower()
    if e in {"prod", "prod-local", "prod-onprem"}:
        return Control(
            "entorn", "Entorn declarat", "ok",
            f"`{s.entorn}` — adequat per a producció.",
        )
    if e in {"pilot", "pilot-gcp"}:
        return Control(
            "entorn", "Entorn declarat", "info",
            f"`{s.entorn}` — pilot/staging.",
            "Canvia a `prod-local` quan operis amb dades reals.",
        )
    return Control(
        "entorn", "Entorn declarat", "avis",
        f"`{s.entorn}` — entorn de desenvolupament.",
        "Defineix `ENTORN=prod-local` al `.env` per a un servidor real.",
    )


def _control_jwt(s: Settings) -> Control:
    js = s.jwt_secret or ""
    if len(js) < 16:
        return Control(
            "jwt_secret", "JWT_SECRET", "critic",
            f"Massa curt ({len(js)} caràcters).",
            "Genera un nou secret: `python -c \"import secrets; print(secrets.token_urlsafe(48))\"`",
        )
    if _feble(js):
        return Control(
            "jwt_secret", "JWT_SECRET", "critic",
            "Conté patrons habituals de desenvolupament (test/dev/demo/canviar).",
            "Substitueix-lo per un valor aleatori fort. Tots els tokens emesos quedaran invalidats.",
        )
    return Control(
        "jwt_secret", "JWT_SECRET", "ok",
        f"Fort (longitud {len(js)}).",
    )


def _control_public_token(s: Settings) -> Control:
    pt = (s.public_chat_token or "").strip()
    if not pt:
        return Control(
            "public_chat_token", "Canal públic", "info",
            "Canal públic DESACTIVAT (PUBLIC_CHAT_TOKEN buit).",
            "Si vols exposar la web del centre al canal públic, configura un token aleatori fort.",
        )
    if _feble(pt):
        return Control(
            "public_chat_token", "PUBLIC_CHAT_TOKEN", "avis",
            "El token conté patrons de desenvolupament.",
            "Generar un nou token aleatori i actualitzar el plugin WP en conseqüència.",
        )
    if len(pt) < 24:
        return Control(
            "public_chat_token", "PUBLIC_CHAT_TOKEN", "avis",
            f"Massa curt ({len(pt)} caràcters).",
            "Mínim recomanat: 32 caràcters aleatoris.",
        )
    return Control(
        "public_chat_token", "PUBLIC_CHAT_TOKEN", "ok",
        f"Fort (longitud {len(pt)}).",
    )


def _control_acces_remot(s: Settings) -> Control:
    if s.acces_remot_admin_only:
        return Control(
            "acces_remot", "Accés remot", "ok",
            "ACCES_REMOT_ADMIN_ONLY=true: només la direcció pot entrar des de fora de la LAN.",
        )
    return Control(
        "acces_remot", "Accés remot", "info",
        "ACCES_REMOT_ADMIN_ONLY=false: tots els rols poden entrar des de qualsevol IP.",
        "En producció amb accés a Internet (VPN/Tailscale), activa'l (true).",
    )


def _control_xarxa_local(s: Settings) -> Control:
    cidrs = [c.strip() for c in (s.xarxa_local_cidrs or "").split(",") if c.strip()]
    massa_ampla = any(
        c in cidrs for c in ("0.0.0.0/0", "::/0", "10.0.0.0/8", "192.168.0.0/16")
    )
    if not cidrs:
        return Control(
            "xarxa_local", "XARXA_LOCAL_CIDRS", "avis",
            "Cap CIDR LAN definit.",
            "Defineix el rang real de la LAN del centre (p. ex. 192.168.0.0/24).",
        )
    if massa_ampla:
        return Control(
            "xarxa_local", "XARXA_LOCAL_CIDRS", "info",
            f"Rangs amplis (RFC1918 sencer): {', '.join(cidrs)}",
            "Restringeix al CIDR específic del centre (p. ex. 192.168.0.0/24).",
        )
    return Control(
        "xarxa_local", "XARXA_LOCAL_CIDRS", "ok",
        f"Rangs LAN definits: {', '.join(cidrs)}",
    )


def _control_credencials_demo() -> Control:
    """Detecta usuaris demo amb la contrasenya per defecte (PBKDF2; no podem
    saber la contrasenya en clar però sí si l'usuari encara existeix amb un
    nom típic de demo)."""
    SessionLocal = get_sessionmaker()
    usuaris_demo = {"admin", "marta", "familia_garcia", "pol", "direccio", "pas_admin"}
    with SessionLocal() as db:
        existents = set(db.scalars(select(User.username).where(User.username.in_(usuaris_demo))).all())
    if not existents:
        return Control(
            "credencials_demo", "Credencials demo", "ok",
            "Cap usuari demo present.",
        )
    return Control(
        "credencials_demo", "Credencials demo", "avis",
        f"Usuaris demo presents: {', '.join(sorted(existents))}.",
        "Canvia o esborra les contrasenyes per defecte abans d'operar amb usuaris reals.",
    )


def _control_audit_log(s: Settings) -> Control:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as db:
        n = db.scalar(select(AuditLog.id).limit(1))
    if n is None:
        return Control(
            "audit_log", "Registre d'auditoria (BD)", "info",
            "Cap entrada a la taula audit_log encara.",
        )
    cami = s.audit_log_path or ""
    if not cami:
        return Control(
            "audit_log", "Registre d'auditoria (BD)", "ok",
            "Còpia a fitxer desactivada; BD com a font autoritzada.",
        )
    if os.path.exists(cami):
        try:
            mida = os.path.getsize(cami)
            return Control(
                "audit_log", "Registre d'auditoria", "ok",
                f"BD + còpia a fitxer ({cami}, {mida} bytes).",
            )
        except OSError:
            pass
    return Control(
        "audit_log", "Registre d'auditoria", "info",
        f"BD activa, però la còpia a fitxer no existeix encara ({cami}).",
    )


def _control_institucions() -> Control:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as db:
        rows = list(db.scalars(select(Institucio)).all())
    actives = [i for i in rows if i.actiu]
    if not rows:
        return Control(
            "institucions", "Institucions actives", "avis",
            "Cap institució creada.",
            "Crea com a mínim 1 institució des d'Administració (superadmin).",
        )
    return Control(
        "institucions", "Institucions actives", "ok",
        f"{len(actives)}/{len(rows)} actives.",
    )


def _control_https() -> Control:
    """Heurística: si el SERVER_HOST conté `https://` o el reverse proxy es
    declara via `PROXY_DE_CONFIANCA=true`, suposem HTTPS configurat."""
    s = get_settings()
    if s.proxy_de_confianca:
        return Control(
            "https", "HTTPS / reverse proxy", "ok",
            "`PROXY_DE_CONFIANCA=true`: assumim TLS terminat al proxy.",
        )
    return Control(
        "https", "HTTPS / reverse proxy", "info",
        "Cap proxy TLS declarat; el backend serveix HTTP en clar a la LAN.",
        "Per a accés des de fora de la LAN, posa un reverse proxy amb HTTPS al davant (Caddy/Traefik/Tailscale Funnel).",
    )


def _control_vector_store(s: Settings) -> Control:
    vs = (s.vector_store or "pgvector").lower()
    if vs == "qdrant":
        return Control(
            "vector_store", "Magatzem vectorial", "ok",
            f"Backend: {vs} (col·leccions físicament separades per namespace).",
        )
    return Control(
        "vector_store", "Magatzem vectorial", "info",
        "Backend: pgvector (apte per a producció mitjana). L'aïllament per "
        "namespace és per filtre, no físic.",
        "Per a producció amb canal públic exposat, considera migrar a Qdrant.",
    )


def _control_telegram(s: Settings) -> Control:
    if (s.telegram_bot_token or "").strip():
        return Control(
            "telegram", "Bot Telegram", "ok",
            "Token configurat. Verifica que el worker estigui en execució.",
        )
    return Control(
        "telegram", "Bot Telegram", "info",
        "Bot desactivat (TELEGRAM_BOT_TOKEN buit).",
    )


# ─────────────────────────── Composició ─────────────────────────────


def executa_check() -> dict[str, Any]:
    s = get_settings()
    controls: list[Control] = [
        _control_entorn(s),
        _control_jwt(s),
        _control_public_token(s),
        _control_acces_remot(s),
        _control_xarxa_local(s),
        _control_credencials_demo(),
        _control_audit_log(s),
        _control_institucions(),
        _control_https(),
        _control_vector_store(s),
        _control_telegram(s),
    ]
    severitat_global = "ok"
    for c in controls:
        if _ORDRE.get(c.severitat, 0) > _ORDRE.get(severitat_global, 0):
            severitat_global = c.severitat
    return {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "host": socket.gethostname(),
        "entorn": s.entorn,
        "versio": s.versio,
        "server_host": s.server_host,
        "severitat_global": severitat_global,
        "controls": [asdict(c) for c in controls],
        "puntuacio": _puntuacio(controls),
    }


def _puntuacio(controls: list[Control]) -> int:
    """Score 0-100 (100 = tot ok). 'ok'=10, 'info'=6, 'avis'=3, 'critic'=0."""
    if not controls:
        return 0
    pesos = {"ok": 10, "info": 6, "avis": 3, "critic": 0}
    pts = sum(pesos.get(c.severitat, 0) for c in controls)
    max_pts = 10 * len(controls)
    return round(pts * 100 / max_pts)


def formata_text(report: dict[str, Any]) -> str:
    """Render text llegible per a terminal (`scripts/produccio_check.py`)."""
    sym = {"ok": "✓", "info": "ℹ", "avis": "⚠", "critic": "✗"}
    linies = [
        f"Adeptify · Estat de producció — {report['ts']}",
        f"Host: {report['host']}  ·  Entorn: {report['entorn']}  ·  Versió: {report['versio']}",
        f"Severitat global: {report['severitat_global'].upper()}  ·  Puntuació: {report['puntuacio']}/100",
        "─" * 70,
    ]
    for c in report["controls"]:
        s = c["severitat"]
        linies.append(f"  {sym.get(s, '?')} [{s.upper():6}] {c['titol']}: {c['detall']}")
        if c.get("recomanacio"):
            linies.append(f"      → {c['recomanacio']}")
    return "\n".join(linies)
