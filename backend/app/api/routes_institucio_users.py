"""Gestió d'usuaris PER INSTITUCIÓ (admin d'institució = direcció).

La **direcció** gestiona NOMÉS els usuaris del SEU centre: tota operació es força a
`usuari.institucio` (s'ignora qualsevol `institucio_id` que enviï el client). El
**superadmin** segueix gestionant-ho tot via `/api/admin/users`.

Garanties de seguretat (innegociables):
- Aïllament: una direcció no pot llistar, editar ni esborrar usuaris d'un altre centre.
- No-escalada: des d'aquí NO es pot crear ni assignar el rol `superadmin`.
- Auditoria de cada acció.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from sqlalchemy import func, select

from app.api.schemas import UserCreate, UserOut, UsersResponse, UserUpdate
from app.core import audit, institucions, llicencia, users
from app.core.roles import Rol
from app.core.security import Usuari, get_current_user
from app.db.models import User
from app.db.session import get_db

router = APIRouter(prefix="/api/institucio/users", tags=["usuaris-institució"])

ROLS_ADMIN_INSTITUCIO = {Rol.DIRECCIO, Rol.SUPERADMIN}


def requereix_admin_institucio(usuari: Usuari = Depends(get_current_user)) -> Usuari:
    if usuari.rol not in ROLS_ADMIN_INSTITUCIO:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Només la direcció pot gestionar els usuaris del centre.",
        )
    return usuari


def _user_out(u: User) -> UserOut:
    return UserOut(
        username=u.username, rol=u.rol, nom=u.nom, email=u.email, actiu=u.actiu,
        institucio_id=getattr(u, "institucio_id", "nou_patufet") or "nou_patufet",
        creat_el=u.creat_el.isoformat() if u.creat_el else None,
        ultim_acces=u.ultim_acces.isoformat() if u.ultim_acces else None,
    )


def _no_superadmin(rol: str | None) -> None:
    """Evita l'escalada de privilegis: la direcció no pot crear/assignar superadmin."""
    if rol == Rol.SUPERADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No es pot crear ni assignar el rol superadmin des de la gestió del centre.",
        )


@router.get("", response_model=UsersResponse)
def llista(
    admin: Usuari = Depends(requereix_admin_institucio),
    db: Session = Depends(get_db),
) -> UsersResponse:
    files = users.llista_usuaris(db, institucio_id=admin.institucio)
    return UsersResponse(users=[_user_out(u) for u in files])


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def crea(
    cos: UserCreate,
    admin: Usuari = Depends(requereix_admin_institucio),
    db: Session = Depends(get_db),
) -> UserOut:
    _no_superadmin(cos.rol)
    # Quota de llicència: nombre màxim d'usuaris del pla (0 = il·limitat).
    inst = institucions.obte(db, admin.institucio)
    n_usuaris = int(db.scalar(
        select(func.count(User.id)).where(User.institucio_id == admin.institucio)
    ) or 0)
    if not llicencia.dins_de_limit(inst.config if inst else None, "max_usuaris", n_usuaris):
        lim = llicencia.limit(inst.config if inst else None, "max_usuaris")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"S'ha assolit el límit d'usuaris del pla ({lim}). "
                   "Amplia la llicència per donar d'alta més usuaris.",
        )
    try:
        # FORÇA la institució del caller (s'ignora cos.institucio_id).
        u = users.crea_usuari(
            db, cos.username, cos.contrasenya, cos.rol,
            nom=cos.nom, email=cos.email, actiu=cos.actiu,
            institucio_id=admin.institucio,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    audit.registra_accio(
        db, usuari=admin.usuari, rol=admin.rol.value, accio="user_create",
        detalls={"username": cos.username, "rol": cos.rol, "institucio": admin.institucio},
    )
    return _user_out(u)


@router.put("/{username}", response_model=UserOut)
def actualitza(
    username: str,
    cos: UserUpdate,
    admin: Usuari = Depends(requereix_admin_institucio),
    db: Session = Depends(get_db),
) -> UserOut:
    _no_superadmin(cos.rol)
    try:
        # Scoped a la institució del caller: si l'usuari no hi és, retorna None → 404.
        u = users.actualitza_usuari(
            db, username, institucio_id=admin.institucio, rol=cos.rol, nom=cos.nom,
            email=cos.email, actiu=cos.actiu, contrasenya=cos.contrasenya,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if u is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuari no trobat al teu centre.")
    audit.registra_accio(
        db, usuari=admin.usuari, rol=admin.rol.value, accio="user_update",
        detalls={"username": username, "institucio": admin.institucio,
                 "canvis": cos.model_dump(exclude_none=True, exclude={"contrasenya"})},
    )
    return _user_out(u)


@router.delete("/{username}")
def esborra(
    username: str,
    admin: Usuari = Depends(requereix_admin_institucio),
    db: Session = Depends(get_db),
) -> dict:
    if username == admin.usuari:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No et pots esborrar a tu mateix.",
        )
    existia = users.esborra_usuari(db, username, admin.institucio)  # scoped al centre
    audit.registra_accio(
        db, usuari=admin.usuari, rol=admin.rol.value, accio="user_delete",
        detalls={"username": username, "institucio": admin.institucio, "existia": existia},
    )
    if not existia:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuari no trobat al teu centre.")
    return {"esborrat": True, "username": username}
