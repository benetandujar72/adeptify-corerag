"""Seguretat: emissió i verificació de tokens JWT i dependència d'usuari actual.

Al MVP l'autenticació és simple: un endpoint de login emet un JWT que codifica
l'usuari i el rol. La resta d'endpoints en deriven l'usuari via la dependència
`get_current_user` de FastAPI. En el futur s'hi connectarà SSO Clickedu.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException, Request, status

from app.core.config import Settings, get_settings
from app.core.roles import Rol, es_rol_valid

# Rols que poden accedir de forma REMOTA (fora de la xarxa local) quan el control
# d'accés remot està actiu. La resta de rols, només des de la xarxa del centre.
ROLS_ACCES_REMOT: tuple[Rol, ...] = (Rol.DIRECCIO, Rol.SUPERADMIN)


@dataclass(frozen=True)
class Usuari:
    """Identitat autenticada extreta del token."""

    usuari: str
    rol: Rol
    institucio: str = "nou_patufet"  # slug del tenant (multi-institució)
    token_version: int = 0  # claim `tv`; es compara amb User.token_version


# Issuer/Audience del JWT (verificats al descodificar): el token només és vàlid
# per a aquesta aplicació i no es pot reutilitzar amb un altre servei.
_JWT_ISS = "adeptify"
_JWT_AUD = "adeptify"


def crea_token(
    usuari: str,
    rol: Rol,
    institucio: str = "nou_patufet",
    settings: Settings | None = None,
    token_version: int = 0,
) -> str:
    """Emet un JWT signat amb l'usuari, el rol i la institució (tenant).

    Inclou `tv` (token_version) per poder revocar tokens, i `iss`/`aud` per
    acotar-ne l'ús. El token caduca segons `jwt_expira_hores`.
    """
    settings = settings or get_settings()
    ara = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": usuari,
        "rol": rol.value if isinstance(rol, Rol) else str(rol),
        "inst": institucio,
        "tv": int(token_version),
        "iss": _JWT_ISS,
        "aud": _JWT_AUD,
        "iat": ara,
        "exp": ara + dt.timedelta(hours=settings.jwt_expira_hores),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def descodifica_token(token: str, settings: Settings | None = None) -> Usuari:
    """Verifica el token (signatura, caducitat, issuer, audience) i retorna
    l'usuari. Llança 401 si és invàlid."""
    settings = settings or get_settings()
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm],
            audience=_JWT_AUD, issuer=_JWT_ISS,
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El token ha caducat.",
        ) from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invàlid.",
        ) from exc

    sub = payload.get("sub")
    rol = payload.get("rol")
    if not sub or not rol or not es_rol_valid(rol):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sense identitat o rol vàlids.",
        )
    institucio = payload.get("inst") or "nou_patufet"
    tv = int(payload.get("tv", 0) or 0)
    return Usuari(usuari=sub, rol=Rol(rol), institucio=institucio, token_version=tv)


def _revalida_contra_bd(db, usuari: "Usuari") -> "Usuari":
    """Revalida la identitat del token contra la fila d'usuari (si existeix):

    - usuari desactivat (`actiu=False`)            → 401 (desactivació immediata)
    - `token_version` no coincideix               → 401 (logout/canvi de contrasenya)
    - rol diferent a la BD                         → mana la BD (degradació de rol)

    Si NO hi ha fila (p. ex. tokens sintètics de test o desplegaments sense taula
    d'usuaris encara), es confia en el token (comportament previ). La supressió
    DURA d'un usuari (fila esborrada) queda coberta per la caducitat del token.
    """
    from sqlalchemy import select

    from app.db.models import User

    row = db.scalar(
        select(User).where(
            User.username == usuari.usuari,
            User.institucio_id == usuari.institucio,
        )
    )
    if row is None:
        return usuari
    if not row.actiu:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El compte està desactivat.",
        )
    if int(getattr(row, "token_version", 0) or 0) != usuari.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sessió s'ha revocat. Torna a iniciar sessió.",
        )
    if es_rol_valid(row.rol) and row.rol != usuari.rol.value:
        # El rol persistit mana (protegeix de degradacions de rol no aplicades).
        return Usuari(
            usuari=usuari.usuari, rol=Rol(row.rol),
            institucio=usuari.institucio, token_version=usuari.token_version,
        )
    return usuari


# ── Control d'accés remot (Fase 1) ──────────────────────────────────────────


@lru_cache(maxsize=16)
def _xarxes_local(cidrs_str: str) -> tuple:
    """Parseja una cadena de CIDRs separats per comes a objectes ip_network."""
    nets = []
    for tros in cidrs_str.split(","):
        tros = tros.strip()
        if not tros:
            continue
        try:
            nets.append(ipaddress.ip_network(tros, strict=False))
        except ValueError:
            continue  # ignora entrades malformades
    return tuple(nets)


def _es_ip_local(ip: str | None, cidrs_str: str) -> bool:
    """Cert si `ip` pertany a algun dels rangs CIDR de xarxa local."""
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False  # IP no parsejable → es tracta com a NO local (fail-closed)
    return any(addr in net for net in _xarxes_local(cidrs_str))


def ip_de_peticio(request: Request | None, settings: Settings) -> str | None:
    """IP del client. Darrere proxy de confiança, usa el primer X-Forwarded-For;
    altrament, la IP directa del socket (evita falsejament de la capçalera)."""
    if request is None:
        return None
    if settings.proxy_de_confianca:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else None


def acces_es_remot(request: Request | None, settings: Settings) -> bool:
    """Cert si la petició NO prové de la xarxa local (segons l'allow-list)."""
    return not _es_ip_local(ip_de_peticio(request, settings), settings.xarxa_local_cidrs)


def comprova_acces_remot(request: Request | None, usuari: Usuari, settings: Settings) -> None:
    """Si el control és actiu i l'accés és remot, només l'autoritza als rols
    d'administració; altrament llança 403. Des de la xarxa local no restringeix."""
    if not settings.acces_remot_admin_only:
        return
    if not acces_es_remot(request, settings):
        return  # accés des de la xarxa local → permès
    if usuari.rol in ROLS_ACCES_REMOT:
        return  # accés remot però rol d'administració → permès
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "Accés remot restringit al rol d'administració. "
            "Connecta't des de la xarxa del centre per a aquest rol."
        ),
    )


def comprova_acces_xarxa_institucio(
    request: Request | None,
    usuari: Usuari,
    settings: Settings,
    db,
) -> None:
    """Aplica la política d'accés per IP DEFINIDA PER LA INSTITUCIÓ. Es complementa
    amb el control global del `.env` (que la pot relaxar o estrènyer). Si la
    política està activa i la IP no encaixa, llança 403.

    Excepció: la direcció i el superadmin NO es bloquegen mai per aquesta política
    (han de poder entrar a corregir-la si s'han bloquejat a si mateixos)."""
    # Import diferit per evitar cicle amb db/models i amb el router de seguretat.
    from app.core import acces_xarxa
    from app.core import audit as _audit

    if usuari.rol in ROLS_ACCES_REMOT:
        return  # direcció/superadmin: by-pass per no quedar mai bloquejats
    try:
        politica = acces_xarxa.politica_per_institucio(db, usuari.institucio)
    except Exception:
        return  # tolerant: si la BD falla, no bloqueja per aquest motiu
    if not politica.get("actiu"):
        return
    ip = ip_de_peticio(request, settings)
    if acces_xarxa.ip_permesa(ip, politica):
        return
    try:
        _audit.registra_accio(
            db, usuari=usuari.usuari, rol=usuari.rol.value, accio="acces_xarxa_denegat",
            detalls={"institucio": usuari.institucio, "ip": ip},
        )
    except Exception:
        pass
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "La teva IP no està autoritzada per accedir a aquest centre. "
            "Connecta't des de la xarxa del centre o demana a la direcció "
            "que t'afegeixi a la llista d'IPs permeses."
        ),
    )


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Usuari:
    """Dependència FastAPI: extreu l'usuari de la capçalera Authorization i aplica
    el control d'accés remot (només administració des de fora de la xarxa local)
    + la política d'accés per IP/CIDR DE LA INSTITUCIÓ (si està activa).

    Format esperat: `Authorization: Bearer <token>`.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta la capçalera Authorization: Bearer <token>.",
        )
    token = authorization.split(" ", 1)[1].strip()
    usuari = descodifica_token(token, settings)
    comprova_acces_remot(request, usuari, settings)
    # Política per institució: obrim una sessió curta (no podem usar Depends(get_db)
    # aquí perquè això mateix és una dependència). La cache redueix la càrrega.
    try:
        from app.db.session import get_sessionmaker

        sessio = get_sessionmaker()()
        try:
            # Revalida contra la BD (desactivació/revocació/degradació de rol).
            usuari = _revalida_contra_bd(sessio, usuari)
            comprova_acces_xarxa_institucio(request, usuari, settings, sessio)
        finally:
            sessio.close()
    except HTTPException:
        raise
    except Exception:
        # Si la BD no està disponible (p. ex. en alguns tests molt primitius), no
        # bloquegem per aquest motiu — la resta del backend no funcionaria igualment.
        pass
    return usuari
