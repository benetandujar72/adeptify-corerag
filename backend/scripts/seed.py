"""Script de seed: ingesta de sample_data + usuaris demo per rol.

Ús (dins el contenidor o amb el venv actiu):

    python -m scripts.seed

- Crea les taules (si no existeixen).
- Ingesta tots els documents de `SAMPLE_DATA_PATH` (per defecte /app/sample_data).
- Emet un token JWT demo per a cada rol (docent, alumne, familia, direccio) i
  els imprimeix per pantalla per facilitar les proves del frontend.

Reutilitza EXACTAMENT el mateix codi d'ingesta que /api/ingest
(app.ingest.pipeline), de manera que no hi ha divergència entre seed i API.
"""

from __future__ import annotations

import sys

from app.core import users
from app.core.config import get_settings
from app.core.roles import Rol
from app.db.models import Base
from app.db.session import get_engine, get_sessionmaker
from app.ingest import pipeline

DEFAULT_PWD = "patufet2026"
SUPERADMIN_PWD = "admin-patufet-2026"


def crea_taules() -> None:
    Base.metadata.create_all(bind=get_engine())


def ingesta_sample_data() -> tuple[int, int]:
    settings = get_settings()
    sessio = get_sessionmaker()()
    try:
        return pipeline.ingesta_carpeta(sessio, settings.sample_data_path)
    finally:
        sessio.close()


def crea_usuaris_demo() -> list[tuple[str, str, str]]:
    """Crea (idempotent) els usuaris demo + el superadmin amb contrasenya hashejada.

    Retorna una llista (username, rol, contrasenya) per imprimir-la. No canvia els
    usuaris que ja existeixen (les contrasenyes canviades es conserven).
    """
    demo = [
        ("admin", Rol.SUPERADMIN, SUPERADMIN_PWD, "Superadministrador"),
        ("marta", Rol.DOCENT, DEFAULT_PWD, "Marta Rodríguez"),
        ("pol", Rol.ALUMNE, DEFAULT_PWD, "Pol"),
        ("familia_garcia", Rol.FAMILIA, DEFAULT_PWD, "Família Garcia"),
        ("direccio", Rol.DIRECCIO, DEFAULT_PWD, "Direcció"),
        ("pas_admin", Rol.PAS, DEFAULT_PWD, "Administració / PAS"),
    ]
    sessio = get_sessionmaker()()
    creds: list[tuple[str, str, str]] = []
    try:
        for username, rol, pwd, nom in demo:
            users.assegura_usuari(sessio, username, pwd, rol, nom)
            creds.append((username, rol.value, pwd))
    finally:
        sessio.close()
    return creds


def main() -> int:
    print("→ Creant taules…")
    crea_taules()

    print("→ Institució per defecte…")
    from app.core import institucions as _inst

    _s = get_sessionmaker()()
    try:
        _inst.assegura(_s, "nou_patufet", "Escola Nou Patufet")
        print("  ✓ institució 'nou_patufet'")
    finally:
        _s.close()

    print("→ Ingerint sample_data…")
    try:
        docs, chunks = ingesta_sample_data()
        print(f"  ✓ {docs} documents nous, {chunks} chunks indexats.")
    except FileNotFoundError as exc:
        print(f"  ! No s'ha pogut ingerir: {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"  ! Error d'ingesta: {exc}")

    print("→ Usuaris (login amb usuari + contrasenya):")
    for username, rol, pwd in crea_usuaris_demo():
        print(f"  · {rol:11} usuari={username:16} contrasenya={pwd}")

    print("\nLlest. Inicia sessió a /api/auth/login amb {usuari, contrasenya}.")
    print("IMPORTANT: canvia les contrasenyes per defecte en producció.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
