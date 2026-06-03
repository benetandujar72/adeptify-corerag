"""Servei d'institucions (tenants). CRUD i utilitats de multi-tenant.

Cada institució té un `slug` únic que identifica el seu RAG aïllat. Els documents,
usuaris i converses porten `institucio_id` = slug, i totes les consultes s'hi filtren.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Institucio


def llista(db: Session) -> list[Institucio]:
    return list(db.scalars(select(Institucio).order_by(Institucio.slug)).all())


def obte(db: Session, slug: str) -> Institucio | None:
    return db.scalar(select(Institucio).where(Institucio.slug == slug))


def crea(
    db: Session,
    slug: str,
    nom: str,
    *,
    config: dict | None = None,
    branding: dict | None = None,
) -> Institucio:
    if obte(db, slug) is not None:
        raise ValueError(f"La institució ja existeix: {slug}")
    inst = Institucio(slug=slug, nom=nom, config=config, branding=branding)
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


def actualitza(
    db: Session,
    slug: str,
    *,
    nom: str | None = None,
    actiu: bool | None = None,
    config: dict | None = None,
    branding: dict | None = None,
) -> Institucio | None:
    inst = obte(db, slug)
    if inst is None:
        return None
    if nom is not None:
        inst.nom = nom
    if actiu is not None:
        inst.actiu = actiu
    if config is not None:
        inst.config = config
    if branding is not None:
        inst.branding = branding
    db.commit()
    db.refresh(inst)
    return inst


def esborra(db: Session, slug: str) -> bool:
    inst = obte(db, slug)
    if inst is None:
        return False
    db.delete(inst)
    db.commit()
    return True


def assegura(db: Session, slug: str, nom: str) -> None:
    """Crea la institució si no existeix (idempotent, per al seed)."""
    if obte(db, slug) is None:
        crea(db, slug, nom)
