"""Seguretat de xarxa per institució (Fase 1 — extensió per institució).

Permet a la **direcció** (o al superadmin) configurar les IPs/CIDRs permesos del
SEU centre, com a complement (i refinament) del control global d'accés remot.

Endpoints (prefix `/api/institucio/seguretat`):
- GET    /xarxa            llegeix la política i indica si la IP actual hi entra.
- PUT    /xarxa            actualitza-la (només direcció/superadmin).
- GET    /xarxa/detecta    proposa un CIDR a partir de la IP del peticionari.

Aïllament: tot es lliga a `usuari.institucio`. Una direcció no pot tocar
política d'una altra institució (multi-tenant garantit pel token).

Compatibilitat: si la política no està activa, la del `.env` (XARXA_LOCAL_CIDRS)
segueix sent l'única que actua. Quan s'activa, la institució té el control.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.schemas import AccesXarxaOut, AccesXarxaUpdate, DeteccioXarxaResponse
from app.core import acces_xarxa, audit, institucions
from app.core.config import Settings, get_settings
from app.core.roles import Rol
from app.core.security import Usuari, get_current_user, ip_de_peticio

router = APIRouter(prefix="/api/institucio/seguretat", tags=["seguretat"])

ROLS_ADMIN_INST = {Rol.DIRECCIO, Rol.SUPERADMIN}


def requereix_admin_institucio(usuari: Usuari = Depends(get_current_user)) -> Usuari:
    """Només la direcció del centre (o el superadmin) pot configurar la xarxa."""
    if usuari.rol not in ROLS_ADMIN_INST:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Només la direcció del centre (o el superadmin) pot gestionar "
                   "l'accés de xarxa.",
        )
    return usuari


def _carrega_inst(db: Session, usuari: Usuari):
    inst = institucions.obte(db, usuari.institucio)
    if inst is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La institució de l'usuari no existeix.",
        )
    return inst


from app.db.session import get_db


@router.get("/xarxa", response_model=AccesXarxaOut)
def get_xarxa(
    request: Request,
    usuari: Usuari = Depends(requereix_admin_institucio),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AccesXarxaOut:
    inst = _carrega_inst(db, usuari)
    politica = acces_xarxa.llegeix(inst.config)
    ip = ip_de_peticio(request, settings)
    return AccesXarxaOut(
        actiu=politica["actiu"],
        cidrs_lan=politica["cidrs_lan"],
        ips_permeses=politica["ips_permeses"],
        actualitzat_el=politica["actualitzat_el"],
        actualitzat_per=politica["actualitzat_per"],
        ip_actual=ip,
        ip_actual_permesa=acces_xarxa.ip_permesa(ip, politica) if politica["actiu"] else True,
    )


@router.put("/xarxa", response_model=AccesXarxaOut)
def put_xarxa(
    cos: AccesXarxaUpdate,
    request: Request,
    usuari: Usuari = Depends(requereix_admin_institucio),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AccesXarxaOut:
    inst = _carrega_inst(db, usuari)

    # Validem CIDRs/IPs i refusem si n'hi ha d'invàlides (no acceptem barreja silenciosa).
    invalides: list[str] = []
    cidrs_valids = None
    ips_valides = None
    if cos.cidrs_lan is not None:
        cidrs_valids, inval = acces_xarxa.valida_entrades(cos.cidrs_lan)
        invalides += [("cidrs_lan", e) for e in inval]
    if cos.ips_permeses is not None:
        ips_valides, inval = acces_xarxa.valida_entrades(cos.ips_permeses)
        invalides += [("ips_permeses", e) for e in inval]
    if invalides:
        partides = ", ".join(f"{camp}: «{v}»" for camp, v in invalides)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Entrades de xarxa invàlides — {partides}.",
        )

    # Safeguard: si s'ACTIVA la política però l'admin que ho fa no quedaria DINS
    # del rang, ho refusem (per evitar que es bloquegi a si mateix sense possibilitat
    # de tornar a entrar). La direcció pot saltar-se aquesta protecció enviant
    # `actiu=False` o ampliant primer els CIDRs.
    nova_actiu = cos.actiu if cos.actiu is not None else acces_xarxa.llegeix(inst.config)["actiu"]
    if nova_actiu:
        ip_admin = ip_de_peticio(request, settings)
        # Calcula la política "previsualitzada".
        prev = acces_xarxa.llegeix(inst.config)
        prev["actiu"] = True
        if cidrs_valids is not None:
            prev["cidrs_lan"] = cidrs_valids
        if ips_valides is not None:
            prev["ips_permeses"] = ips_valides
        if not acces_xarxa.ip_permesa(ip_admin, prev):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"La teva IP actual ({ip_admin or '?'}) no està dins dels rangs "
                    "proposats. Afegeix-la a la white-list o amplia els CIDRs LAN abans "
                    "d'activar la política, o quedaràs bloquejat."
                ),
            )

    nou_config = acces_xarxa.fusiona(
        inst.config,
        actiu=cos.actiu,
        cidrs_lan=cidrs_valids,
        ips_permeses=ips_valides,
        actualitzat_per=usuari.usuari,
    )
    institucions.actualitza(db, usuari.institucio, config=nou_config)
    acces_xarxa.invalida_cache(usuari.institucio)
    audit.registra_accio(
        db, usuari=usuari.usuari, rol=usuari.rol.value, accio="acces_xarxa_update",
        detalls={
            "institucio": usuari.institucio,
            "actiu": nou_config[acces_xarxa.CONFIG_KEY]["actiu"],
            "n_cidrs_lan": len(nou_config[acces_xarxa.CONFIG_KEY]["cidrs_lan"]),
            "n_ips_permeses": len(nou_config[acces_xarxa.CONFIG_KEY]["ips_permeses"]),
        },
    )
    db.refresh(inst)
    politica = acces_xarxa.llegeix(inst.config)
    ip_actual = ip_de_peticio(request, settings)
    return AccesXarxaOut(
        actiu=politica["actiu"],
        cidrs_lan=politica["cidrs_lan"],
        ips_permeses=politica["ips_permeses"],
        actualitzat_el=politica["actualitzat_el"],
        actualitzat_per=politica["actualitzat_per"],
        ip_actual=ip_actual,
        ip_actual_permesa=acces_xarxa.ip_permesa(ip_actual, politica) if politica["actiu"] else True,
    )


@router.get("/xarxa/detecta", response_model=DeteccioXarxaResponse)
def detecta_xarxa(
    request: Request,
    usuari: Usuari = Depends(requereix_admin_institucio),  # noqa: ARG001
    settings: Settings = Depends(get_settings),
) -> DeteccioXarxaResponse:
    """A partir de la IP del peticionari, proposa un CIDR LAN si és privada.
    Útil per al botó «Detecta xarxa local» del wizard."""
    ip = ip_de_peticio(request, settings)
    cidr = acces_xarxa.proposa_cidr_lan(ip)
    if cidr:
        msg = f"La IP {ip} sembla privada. Suggerim afegir {cidr} com a xarxa LAN."
    elif ip:
        msg = (
            f"La IP {ip} no és privada (sembla pública). Afegeix-la a la white-list "
            "si vols que pugui accedir, o accedeix des de la xarxa del centre."
        )
    else:
        msg = "No s'ha pogut determinar la IP del peticionari."
    return DeteccioXarxaResponse(
        ip_actual=ip, es_local=cidr is not None, cidr_suggerit=cidr, missatge=msg,
    )
