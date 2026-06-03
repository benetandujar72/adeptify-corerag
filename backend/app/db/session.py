"""Sessió i motor SQLAlchemy.

El motor es crea de forma mandrosa la primera vegada que es demana, perquè la
importació del paquet no exigeixi una connexió viva (els tests poden no tenir
Postgres). La dependència `get_db` de FastAPI obre i tanca una sessió per
petició.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Crea (un cop) el motor SQLAlchemy a partir de DATABASE_URL."""
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    """Factory de sessions memoïtzada."""
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )


def get_db() -> Iterator[Session]:
    """Dependència FastAPI: una sessió per petició, tancada en acabar."""
    sessio = get_sessionmaker()()
    try:
        yield sessio
    finally:
        sessio.close()
