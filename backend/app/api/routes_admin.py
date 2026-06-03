"""Endpoints d'administració (NOMÉS superadmin).

- CRUD d'usuaris: /api/admin/users
- Visor del registre d'auditoria forense: /api/admin/audit

El superadmin gestiona tota la plataforma. Tota acció queda auditada.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    AuditEntry,
    AuditResponse,
    InstitucioCreate,
    InstitucioOut,
    InstitucionsResponse,
    InstitucioUpdate,
    UserCreate,
    UserOut,
    UsersResponse,
    UserUpdate,
)
from pydantic import BaseModel

from app.core import audit, institucions, llicencia, users
from app.core.roles import Rol
from app.core.security import Usuari, get_current_user
from app.db.models import AuditLog, Document, Institucio, User
from app.db.session import get_db

router = APIRouter(prefix="/api/admin", tags=["administració"])


def requereix_superadmin(usuari: Usuari = Depends(get_current_user)) -> Usuari:
    """Dependència: només permet l'accés al rol superadmin."""
    if usuari.rol != Rol.SUPERADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Només el superadmin pot accedir a l'administració.",
        )
    return usuari


def _user_out(u: User) -> UserOut:
    return UserOut(
        username=u.username,
        rol=u.rol,
        nom=u.nom,
        email=u.email,
        actiu=u.actiu,
        institucio_id=getattr(u, "institucio_id", "nou_patufet") or "nou_patufet",
        creat_el=u.creat_el.isoformat() if u.creat_el else None,
        ultim_acces=u.ultim_acces.isoformat() if u.ultim_acces else None,
    )


def _inst_out(i: Institucio) -> InstitucioOut:
    return InstitucioOut(
        slug=i.slug,
        nom=i.nom,
        actiu=i.actiu,
        config=i.config,
        branding=i.branding,
        creat_el=i.creat_el.isoformat() if i.creat_el else None,
    )


@router.get("/users", response_model=UsersResponse)
def llista_usuaris(
    admin: Usuari = Depends(requereix_superadmin),
    db: Session = Depends(get_db),
) -> UsersResponse:
    return UsersResponse(users=[_user_out(u) for u in users.llista_usuaris(db)])


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def crea_usuari(
    cos: UserCreate,
    admin: Usuari = Depends(requereix_superadmin),
    db: Session = Depends(get_db),
) -> UserOut:
    try:
        u = users.crea_usuari(
            db, cos.username, cos.contrasenya, cos.rol,
            nom=cos.nom, email=cos.email, actiu=cos.actiu,
            institucio_id=cos.institucio_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    audit.registra_accio(
        db, usuari=admin.usuari, rol=admin.rol.value, accio="user_create",
        detalls={"username": cos.username, "rol": cos.rol},
    )
    return _user_out(u)


@router.put("/users/{username}", response_model=UserOut)
def actualitza_usuari(
    username: str,
    cos: UserUpdate,
    admin: Usuari = Depends(requereix_superadmin),
    db: Session = Depends(get_db),
    institucio: str | None = Query(default=None, description="Institució de l'usuari (username únic per institució)"),
) -> UserOut:
    try:
        u = users.actualitza_usuari(
            db, username, institucio_id=institucio, rol=cos.rol, nom=cos.nom,
            email=cos.email, actiu=cos.actiu, contrasenya=cos.contrasenya,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if u is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuari no trobat.")
    audit.registra_accio(
        db, usuari=admin.usuari, rol=admin.rol.value, accio="user_update",
        detalls={"username": username, "institucio": u.institucio_id, "canvis": cos.model_dump(exclude_none=True, exclude={"contrasenya"})},
    )
    return _user_out(u)


@router.delete("/users/{username}")
def esborra_usuari(
    username: str,
    admin: Usuari = Depends(requereix_superadmin),
    db: Session = Depends(get_db),
    institucio: str | None = Query(default=None, description="Institució de l'usuari"),
) -> dict:
    if username == admin.usuari and (institucio is None or institucio == admin.institucio):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No et pots esborrar a tu mateix.",
        )
    existia = users.esborra_usuari(db, username, institucio)
    audit.registra_accio(
        db, usuari=admin.usuari, rol=admin.rol.value, accio="user_delete",
        detalls={"username": username, "institucio": institucio, "existia": existia},
    )
    if not existia:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuari no trobat.")
    return {"esborrat": True, "username": username}


@router.get("/audit", response_model=AuditResponse)
def visor_auditoria(
    admin: Usuari = Depends(requereix_superadmin),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    usuari: str | None = None,
    accio: str | None = None,
) -> AuditResponse:
    """Registre forense d'accions (append-only), amb filtres opcionals."""
    base = select(AuditLog)
    if usuari:
        base = base.where(AuditLog.usuari == usuari)
    if accio:
        base = base.where(AuditLog.accio == accio)
    total = db.scalar(
        select(func.count()).select_from(base.subquery())
    ) or 0
    files = db.scalars(
        base.order_by(AuditLog.creat_el.desc()).limit(limit).offset(offset)
    ).all()
    entrades = [
        AuditEntry(
            id=a.id,
            usuari=a.usuari,
            rol=a.rol,
            accio=a.accio,
            agent=a.agent,
            conversation_id=a.conversation_id,
            detalls=a.detalls,
            creat_el=a.creat_el.isoformat() if a.creat_el else "",
        )
        for a in files
    ]
    return AuditResponse(entrades=entrades, total=int(total))


# ───────────────────────── Institucions (tenants) ───────────────────────────


@router.get("/institucions", response_model=InstitucionsResponse)
def llista_institucions(
    admin: Usuari = Depends(requereix_superadmin),
    db: Session = Depends(get_db),
) -> InstitucionsResponse:
    return InstitucionsResponse(institucions=[_inst_out(i) for i in institucions.llista(db)])


@router.post("/institucions", response_model=InstitucioOut, status_code=status.HTTP_201_CREATED)
def crea_institucio(
    cos: InstitucioCreate,
    admin: Usuari = Depends(requereix_superadmin),
    db: Session = Depends(get_db),
) -> InstitucioOut:
    try:
        inst = institucions.crea(
            db, cos.slug, cos.nom, config=cos.config, branding=cos.branding
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    audit.registra_accio(
        db, usuari=admin.usuari, rol=admin.rol.value, accio="institucio_create",
        detalls={"slug": cos.slug, "nom": cos.nom},
    )
    return _inst_out(inst)


@router.put("/institucions/{slug}", response_model=InstitucioOut)
def actualitza_institucio(
    slug: str,
    cos: InstitucioUpdate,
    admin: Usuari = Depends(requereix_superadmin),
    db: Session = Depends(get_db),
) -> InstitucioOut:
    inst = institucions.actualitza(
        db, slug, nom=cos.nom, actiu=cos.actiu, config=cos.config, branding=cos.branding
    )
    if inst is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institució no trobada.")
    audit.registra_accio(
        db, usuari=admin.usuari, rol=admin.rol.value, accio="institucio_update",
        detalls={"slug": slug},
    )
    return _inst_out(inst)


@router.delete("/institucions/{slug}")
def esborra_institucio(
    slug: str,
    admin: Usuari = Depends(requereix_superadmin),
    db: Session = Depends(get_db),
) -> dict:
    if slug == "nou_patufet":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No es pot esborrar la institució per defecte.",
        )
    existia = institucions.esborra(db, slug)
    audit.registra_accio(
        db, usuari=admin.usuari, rol=admin.rol.value, accio="institucio_delete",
        detalls={"slug": slug, "existia": existia},
    )
    if not existia:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institució no trobada.")
    return {"esborrat": True, "slug": slug}


# ───────────────────────── Llicències (operador de flota) ───────────────────


class LlicenciaUpdate(BaseModel):
    pla: str | None = None  # essencial | avancat | enterprise
    features: list[str] | None = None
    limits: dict[str, int] | None = None
    data_inici: str | None = None
    data_caducitat: str | None = None
    estat: str | None = None  # activa | prova | suspesa


@router.get("/plans")
def cataleg_plans(admin: Usuari = Depends(requereix_superadmin)) -> dict:
    """Catàleg de plans comercials i features disponibles."""
    return {"plans": llicencia.cataleg_plans(), "features": llicencia.FEATURES}


@router.get("/flota")
def flota(
    admin: Usuari = Depends(requereix_superadmin),
    db: Session = Depends(get_db),
) -> dict:
    """Panell d'operador: totes les institucions amb pla, estat de llicència i ús
    vs límits. Per a la gestió de la flota de centres."""
    sortida = []
    for inst in institucions.llista(db):
        lic = llicencia.llegeix(inst.config)
        us = {
            "usuaris": int(db.scalar(
                select(func.count(User.id)).where(User.institucio_id == inst.slug)
            ) or 0),
            "documents": int(db.scalar(
                select(func.count(Document.id)).where(Document.institucio_id == inst.slug)
            ) or 0),
        }
        sortida.append({
            "slug": inst.slug,
            "nom": inst.nom,
            "actiu": inst.actiu,
            "pla": lic["pla"],
            "pla_nom": lic["pla_nom"],
            "estat_llicencia": lic["estat"],
            "data_caducitat": lic["data_caducitat"],
            "dies_fins_caducitat": lic["dies_fins_caducitat"],
            "limits": lic["limits"],
            "us": us,
            "n_features": len(lic["features"]),
        })
    return {"centres": sortida}


@router.put("/institucions/{slug}/llicencia")
def actualitza_llicencia(
    slug: str,
    cos: LlicenciaUpdate,
    admin: Usuari = Depends(requereix_superadmin),
    db: Session = Depends(get_db),
) -> dict:
    """Assigna/edita la llicència d'un centre (NOMÉS superadmin/operador)."""
    inst = institucions.obte(db, slug)
    if inst is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institució no trobada.")
    if cos.pla is not None and cos.pla not in llicencia.PLANS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Pla desconegut. Vàlids: {sorted(llicencia.PLANS)}.",
        )
    nou_config = llicencia.fusiona(
        inst.config,
        pla=cos.pla, features=cos.features, limits=cos.limits,
        data_inici=cos.data_inici, data_caducitat=cos.data_caducitat, estat=cos.estat,
    )
    institucions.actualitza(db, slug, config=nou_config)
    audit.registra_accio(
        db, usuari=admin.usuari, rol=admin.rol.value, accio="llicencia_update",
        detalls={"slug": slug, "pla": cos.pla, "estat": cos.estat},
    )
    db.refresh(inst)
    lic = llicencia.llegeix(inst.config)
    return {"slug": slug, "llicencia": lic}
