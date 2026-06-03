"""Revocació de sessions: la identitat del token es revalida contra la BD.

Cobreix el forat de seguretat «un usuari desactivat/amb sessió tancada conserva
accés fins que caduca el token»: ara cada petició comprova `actiu` i `token_version`.
"""

from __future__ import annotations

from app.core import users
from app.core.roles import Rol
from app.core.security import crea_token


def _token(username: str, tv: int = 0) -> dict:
    t = crea_token(username, Rol.DOCENT, institucio="nou_patufet", token_version=tv)
    return {"Authorization": f"Bearer {t}"}


def test_usuari_desactivat_perd_acces_immediat(client, db):
    users.crea_usuari(db, "revtest", "contrasenya-forta-123", Rol.DOCENT.value,
                      institucio_id="nou_patufet")
    h = _token("revtest")
    assert client.get("/api/auth/me", headers=h).status_code == 200
    # La direcció desactiva el compte → el token ja emès deixa de valer a la següent petició.
    users.actualitza_usuari(db, "revtest", institucio_id="nou_patufet", actiu=False)
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_logout_invalida_tokens_existents(client, db):
    users.crea_usuari(db, "logouttest", "contrasenya-forta-123", Rol.DOCENT.value,
                      institucio_id="nou_patufet")
    h = _token("logouttest")
    assert client.post("/api/auth/logout", headers=h).status_code == 200
    # Després del logout (bump de token_version) el mateix token queda revocat.
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_canvi_contrasenya_revoca_sessions(client, db):
    users.crea_usuari(db, "pwtest", "contrasenya-inicial-123", Rol.DOCENT.value,
                      institucio_id="nou_patufet")
    h = _token("pwtest")
    assert client.get("/api/auth/me", headers=h).status_code == 200
    users.actualitza_usuari(db, "pwtest", institucio_id="nou_patufet",
                            contrasenya="contrasenya-nova-456")
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_token_sense_audiencia_rebutjat(client):
    """Un token signat sense la audience/issuer esperats (reutilització) es rebutja."""
    import jwt
    from app.core.config import get_settings

    s = get_settings()
    dolent = jwt.encode({"sub": "x", "rol": "docent", "inst": "nou_patufet"},
                        s.jwt_secret, algorithm=s.jwt_algorithm)
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {dolent}"}).status_code == 401
