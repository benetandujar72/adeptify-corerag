"""Tests de l'MFA/2FA (TOTP): unitat + enrolment + login en dos passos."""

from __future__ import annotations

import time

from app.core import totp


def _codi(secret: str) -> str:
    return totp._codi_per_comptador(secret, int(time.time() // 30))


def _codi_incorrecte(secret: str) -> str:
    bo = _codi(secret)
    return "999999" if bo != "999999" else "111111"


def _login(client, **kw):
    return client.post("/api/auth/login", json=kw)


def test_totp_unitat():
    s = totp.genera_secret()
    assert totp.verifica(s, _codi(s)) is True
    assert totp.verifica(s, "12345") is False  # longitud incorrecta
    assert totp.verifica(s, "abcdef") is False  # no numèric
    assert totp.uri_otpauth(s, "marta").startswith("otpauth://totp/")


def test_mfa_enrolment_i_login_dos_passos(client, db):
    from app.core import users

    users.crea_usuari(db, "dir", "k", "direccio", institucio_id="nou_patufet")
    db.commit()
    tok = _login(client, usuari="dir", contrasenya="k", institucio="nou_patufet").json()["token"]
    h = {"Authorization": f"Bearer {tok}"}

    # Estat inicial: MFA inactiu.
    assert client.get("/api/auth/mfa/estat", headers=h).json()["actiu"] is False

    # Setup → secret + URI otpauth.
    setup = client.post("/api/auth/mfa/setup", headers=h).json()
    secret = setup["secret"]
    assert setup["otpauth_uri"].startswith("otpauth://totp/")

    # Activar amb codi incorrecte → 400; amb codi correcte → actiu.
    assert client.post("/api/auth/mfa/activar", headers=h, json={"codi": _codi_incorrecte(secret)}).status_code == 400
    assert client.post("/api/auth/mfa/activar", headers=h, json={"codi": _codi(secret)}).json()["actiu"] is True

    # Ara el login demana el segon factor (credencials OK però sense token).
    r1 = _login(client, usuari="dir", contrasenya="k", institucio="nou_patufet")
    assert r1.status_code == 200
    assert r1.json()["mfa_required"] is True and r1.json()["token"] == ""

    # Login amb codi correcte → token; amb codi incorrecte → 401.
    r2 = _login(client, usuari="dir", contrasenya="k", institucio="nou_patufet", codi_mfa=_codi(secret))
    assert r2.status_code == 200 and r2.json()["token"] and r2.json()["mfa_required"] is False
    assert _login(client, usuari="dir", contrasenya="k", institucio="nou_patufet", codi_mfa=_codi_incorrecte(secret)).status_code == 401

    # Desactivar → el login torna a funcionar sense codi.
    assert client.post("/api/auth/mfa/desactivar", headers=h).json()["actiu"] is False
    assert _login(client, usuari="dir", contrasenya="k", institucio="nou_patufet").json()["token"]
