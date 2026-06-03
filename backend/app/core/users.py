"""Servei d'usuaris: autenticació i CRUD (RBAC + superadmin).

Encapsula tota la lògica de la taula `users` perquè els routers no toquin l'ORM
directament. Les contrasenyes mai es retornen ni es registren.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import totp
from app.core.passwords import hash_password, verify_password
from app.core.roles import Rol, es_rol_valid
from app.db.models import User


def autentica(
    db: Session, username: str, contrasenya: str, institucio_id: str | None = None
) -> User | None:
    """Retorna l'usuari si les credencials són vàlides i està actiu; si no, None.

    Com que el `username` és únic NOMÉS per institució, pot haver-hi diversos
    usuaris amb el mateix nom (a institucions diferents). Si no s'indica
    `institucio_id`, es prova la contrasenya contra tots els candidats i es
    retorna el que coincideix (recomanació: contrasenyes diferents per institució,
    o afegir el selector d'institució al login).
    """
    stmt = select(User).where(User.username == username)
    if institucio_id:
        stmt = stmt.where(User.institucio_id == institucio_id)
    for user in db.scalars(stmt).all():
        if user.actiu and verify_password(contrasenya, user.password_hash):
            user.ultim_acces = dt.datetime.now(dt.timezone.utc)
            db.commit()
            return user
    return None


def llista_usuaris(db: Session, institucio_id: str | None = None) -> list[User]:
    """Llista d'usuaris. Si s'indica `institucio_id`, NOMÉS els d'aquell centre
    (per a l'administració per institució); sense, tots (superadmin)."""
    stmt = select(User)
    if institucio_id:
        stmt = stmt.where(User.institucio_id == institucio_id)
    return list(db.scalars(stmt.order_by(User.institucio_id, User.username)).all())


def obte_usuari(
    db: Session, username: str, institucio_id: str | None = None
) -> User | None:
    """Obté un usuari. Si s'indica `institucio_id`, cerca dins aquesta institució
    (recomanat ara que el username és únic per institució). Sense institució,
    retorna el primer que coincideixi pel nom (compat)."""
    stmt = select(User).where(User.username == username)
    if institucio_id:
        stmt = stmt.where(User.institucio_id == institucio_id)
    return db.scalar(stmt)


def crea_usuari(
    db: Session,
    username: str,
    contrasenya: str,
    rol: str,
    *,
    nom: str | None = None,
    email: str | None = None,
    actiu: bool = True,
    institucio_id: str = "nou_patufet",
) -> User:
    """Crea un usuari. Llança ValueError si el rol és invàlid o ja existeix a la
    MATEIXA institució (es permet el mateix nom en institucions diferents)."""
    if not es_rol_valid(rol):
        raise ValueError(f"Rol invàlid: {rol}")
    if obte_usuari(db, username, institucio_id) is not None:
        raise ValueError(
            f"L'usuari «{username}» ja existeix a la institució «{institucio_id}»."
        )
    user = User(
        username=username,
        password_hash=hash_password(contrasenya),
        rol=rol,
        nom=nom,
        email=email,
        actiu=actiu,
        institucio_id=institucio_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def actualitza_usuari(
    db: Session,
    username: str,
    *,
    institucio_id: str | None = None,
    rol: str | None = None,
    nom: str | None = None,
    email: str | None = None,
    actiu: bool | None = None,
    contrasenya: str | None = None,
) -> User | None:
    """Actualitza camps d'un usuari. Retorna None si no existeix."""
    user = obte_usuari(db, username, institucio_id)
    if user is None:
        return None
    # Canvis que han d'INVALIDAR els tokens ja emesos (revocació de sessió).
    revoca = False
    if rol is not None:
        if not es_rol_valid(rol):
            raise ValueError(f"Rol invàlid: {rol}")
        if rol != user.rol:
            revoca = True
        user.rol = rol
    if nom is not None:
        user.nom = nom
    if email is not None:
        user.email = email
    if actiu is not None:
        if actiu is False and user.actiu:
            revoca = True
        user.actiu = actiu
    if contrasenya:
        user.password_hash = hash_password(contrasenya)
        revoca = True
    if revoca:
        user.token_version = (user.token_version or 0) + 1
    db.commit()
    db.refresh(user)
    return user


def revoca_sessions(db: Session, username: str, institucio_id: str | None = None) -> bool:
    """Invalida TOTS els tokens emesos per a aquest usuari (logout 'a tot arreu')
    incrementant `token_version`. Retorna True si l'usuari existeix."""
    user = obte_usuari(db, username, institucio_id)
    if user is None:
        return False
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    return True


def esborra_usuari(db: Session, username: str, institucio_id: str | None = None) -> bool:
    """Esborra un usuari. Retorna True si existia."""
    user = obte_usuari(db, username, institucio_id)
    if user is None:
        return False
    db.delete(user)
    db.commit()
    return True


# ───────────────────────── MFA / 2FA (TOTP) ─────────────────────────────────


def inicia_mfa(db: Session, username: str, institucio_id: str | None = None) -> str | None:
    """Genera i desa un secret TOTP (encara NO activat). Retorna el secret o None."""
    user = obte_usuari(db, username, institucio_id)
    if user is None:
        return None
    user.totp_secret = totp.genera_secret()
    user.totp_actiu = False
    db.commit()
    return user.totp_secret


def activa_mfa(db: Session, username: str, codi: str, institucio_id: str | None = None) -> bool:
    """Activa l'MFA si el codi verifica contra el secret desat (enrolment)."""
    user = obte_usuari(db, username, institucio_id)
    if user is None or not user.totp_secret:
        return False
    if not totp.verifica(user.totp_secret, codi):
        return False
    user.totp_actiu = True
    db.commit()
    return True


def desactiva_mfa(db: Session, username: str, institucio_id: str | None = None) -> bool:
    """Desactiva l'MFA i esborra el secret. Retorna True si l'usuari existia."""
    user = obte_usuari(db, username, institucio_id)
    if user is None:
        return False
    user.totp_secret = None
    user.totp_actiu = False
    db.commit()
    return True


def assegura_usuari(
    db: Session,
    username: str,
    contrasenya: str,
    rol: Rol,
    nom: str | None = None,
    institucio_id: str = "nou_patufet",
) -> None:
    """Crea l'usuari si no existeix (idempotent, per al seed). No canvia els existents."""
    if obte_usuari(db, username, institucio_id) is None:
        crea_usuari(
            db, username, contrasenya, rol.value, nom=nom, institucio_id=institucio_id
        )
