"""Política d'accés per IP/CIDR a nivell d'institució.



Cada institució pot definir la seva pròpia llista de **CIDRs LAN** (rangs que es
consideren "del centre") i una **white-list d'IPs/CIDRs** addicionals permeses
(p. ex. la IP pública de la seu d'Adeptify per a manteniment, o una VPN del
director). Si la política està **activa** i la IP del peticionari no encaixa
amb cap dels rangs, la petició es bloqueja amb **403** (auditat).

Compatibilitat: si una institució NO té política definida, s'aplica la política
global del `.env` (`XARXA_LOCAL_CIDRS`) com a fallback (comportament previ).

L'excepció històrica de `ACCES_REMOT_ADMIN_ONLY` segueix vigent: la direcció i el
superadmin poden encara entrar des de fora del rang (per administrar el sistema
remotament) si no se'ls posa explícitament a la deny-list. La política
d'institució no afecta directament a la direcció/superadmin per evitar
deixar-los fora del seu propi sistema.

Es desa a `Institucio.config["acces_xarxa"]`:
    {
        "actiu": bool,
        "cidrs_lan": ["192.168.1.0/24", ...],  # rangs LAN del centre
        "ips_permeses": ["80.34.21.5", "85.0.0.0/16", ...],  # white-list addicional
        "actualitzat_el": "ISO datetime",
        "actualitzat_per": "username",
    }
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import threading
from typing import Any

# Claus emprades dins Institucio.config["acces_xarxa"].
CONFIG_KEY = "acces_xarxa"


def buida() -> dict[str, Any]:
    """Retorna la configuració per defecte (política inactiva, llistes buides)."""
    return {
        "actiu": False,
        "cidrs_lan": [],
        "ips_permeses": [],
        "actualitzat_el": None,
        "actualitzat_per": None,
    }


def llegeix(config: dict | None) -> dict[str, Any]:
    """Extreu i normalitza la sub-config d'accés de xarxa de `Institucio.config`."""
    base = buida()
    if not config:
        return base
    secc = config.get(CONFIG_KEY) or {}
    base["actiu"] = bool(secc.get("actiu", False))
    base["cidrs_lan"] = [str(x) for x in (secc.get("cidrs_lan") or [])]
    base["ips_permeses"] = [str(x) for x in (secc.get("ips_permeses") or [])]
    base["actualitzat_el"] = secc.get("actualitzat_el")
    base["actualitzat_per"] = secc.get("actualitzat_per")
    return base


def fusiona(
    config: dict | None,
    *,
    actiu: bool | None = None,
    cidrs_lan: list[str] | None = None,
    ips_permeses: list[str] | None = None,
    actualitzat_per: str | None = None,
) -> dict[str, Any]:
    """Aplica els canvis sobre `Institucio.config` i en retorna una còpia
    nova (no muta l'original)."""
    nou = dict(config or {})
    secc = dict((config or {}).get(CONFIG_KEY) or {})
    if actiu is not None:
        secc["actiu"] = bool(actiu)
    if cidrs_lan is not None:
        secc["cidrs_lan"] = [_normalitza(c) for c in cidrs_lan if _normalitza(c)]
    if ips_permeses is not None:
        secc["ips_permeses"] = [_normalitza(c) for c in ips_permeses if _normalitza(c)]
    secc["actualitzat_el"] = dt.datetime.now(dt.timezone.utc).isoformat()
    if actualitzat_per:
        secc["actualitzat_per"] = actualitzat_per
    nou[CONFIG_KEY] = secc
    return nou


def _normalitza(entrada: str) -> str | None:
    """Normalitza una IP o CIDR. Una IP individual la deixem tal qual (no com a /32)
    perquè la UI mostri exactament el que l'usuari ha escrit; el parseig per a
    pertinença es fa amb `ipaddress.ip_network(strict=False)`."""
    if not isinstance(entrada, str):
        return None
    entrada = entrada.strip()
    if not entrada:
        return None
    try:
        if "/" in entrada:
            ipaddress.ip_network(entrada, strict=False)
        else:
            ipaddress.ip_address(entrada)
    except ValueError:
        return None
    return entrada


def valida_entrades(entrades: list[str]) -> tuple[list[str], list[str]]:
    """Separa una llista en (vàlides_normalitzades, invàlides_brutes)."""
    valides: list[str] = []
    invalides: list[str] = []
    for e in entrades:
        n = _normalitza(e)
        if n is None:
            invalides.append(e)
        else:
            valides.append(n)
    return valides, invalides


def ip_permesa(ip: str | None, politica: dict[str, Any]) -> bool:
    """Cert si `ip` està a algun CIDR LAN o a la white-list. Si la política no és
    activa, retorna sempre True (no bloqueja). IP no parsejable → False (fail-closed)."""
    if not politica.get("actiu"):
        return True
    if not ip:
        return False  # política activa i IP indeterminada → bloqueja
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for rang in (politica.get("cidrs_lan") or []) + (politica.get("ips_permeses") or []):
        try:
            net = ipaddress.ip_network(rang, strict=False)
        except ValueError:
            continue
        if addr in net:
            return True
    return False


# ── Cache curta per evitar consultes BD a cada petició ───────────────────────
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()
_TTL_SEGONS = 30.0


def politica_per_institucio(db, institucio_id: str) -> dict[str, Any]:
    """Llegeix (amb cache curta) la política de xarxa d'una institució."""
    import time

    from app.db.models import Institucio
    from sqlalchemy import select

    ara = time.monotonic()
    with _cache_lock:
        cached = _cache.get(institucio_id)
        if cached and (ara - cached[0]) < _TTL_SEGONS:
            return cached[1]
    inst = db.scalar(select(Institucio).where(Institucio.slug == institucio_id))
    politica = llegeix(inst.config if inst else None)
    with _cache_lock:
        _cache[institucio_id] = (ara, politica)
    return politica


def invalida_cache(institucio_id: str | None = None) -> None:
    """Buida la cache (per institució o globalment) després d'un PUT."""
    with _cache_lock:
        if institucio_id is None:
            _cache.clear()
        else:
            _cache.pop(institucio_id, None)


def proposa_cidr_lan(ip: str | None) -> str | None:
    """Proposa un CIDR /24 (IPv4) o /64 (IPv6) a partir d'una IP del peticionari,
    si és privada/local (RFC1918, ULA, loopback). Si és pública o desconeguda,
    retorna None. Útil per al botó «Detecta xarxa local» de la UI."""
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if not (addr.is_private or addr.is_loopback):
        return None
    if isinstance(addr, ipaddress.IPv4Address):
        # /24 cobreix el rang típic d'una xarxa de centre/oficina.
        return str(ipaddress.ip_network(f"{addr}/24", strict=False))
    # IPv6: /64 és la subxarxa estàndard.
    return str(ipaddress.ip_network(f"{addr}/64", strict=False))
