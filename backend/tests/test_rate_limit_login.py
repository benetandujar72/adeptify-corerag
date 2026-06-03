"""Tests del rate-limit del login (bloqueig anti força bruta)."""

from __future__ import annotations


def _seed(db):
    from app.core import users

    users.crea_usuari(db, "victima", "bona", "docent", institucio_id="nou_patufet")
    db.commit()


def test_bloqueig_despres_de_massa_fallits(client, db, monkeypatch):
    from app.core.config import get_settings

    _seed(db)
    s = get_settings()
    monkeypatch.setattr(s, "login_max_intents", 3)
    monkeypatch.setattr(s, "login_bloqueig_minuts", 15)

    body_mal = {"usuari": "victima", "contrasenya": "DOLENTA", "institucio": "nou_patufet"}
    # 3 intents fallits → 401 cadascun (credencials incorrectes).
    for _ in range(3):
        assert client.post("/api/auth/login", json=body_mal).status_code == 401
    # El 4t intent (encara que la contrasenya fos correcta) → 429 (bloquejat).
    r = client.post("/api/auth/login", json={"usuari": "victima", "contrasenya": "bona", "institucio": "nou_patufet"})
    assert r.status_code == 429
    assert "intents" in r.json()["error"]["missatge"].lower()


def test_login_correcte_reseteja_el_comptador(client, db, monkeypatch):
    from app.core.config import get_settings

    _seed(db)
    s = get_settings()
    monkeypatch.setattr(s, "login_max_intents", 3)

    mal = {"usuari": "victima", "contrasenya": "x", "institucio": "nou_patufet"}
    be = {"usuari": "victima", "contrasenya": "bona", "institucio": "nou_patufet"}
    # 2 fallits, després un encert → 200 i comptador resetejat.
    assert client.post("/api/auth/login", json=mal).status_code == 401
    assert client.post("/api/auth/login", json=mal).status_code == 401
    assert client.post("/api/auth/login", json=be).status_code == 200
    # Després de l'èxit, es pot tornar a fallar sense quedar bloquejat immediatament.
    assert client.post("/api/auth/login", json=mal).status_code == 401


def test_el_bloqueig_es_per_compte_no_afecta_altres(client, db, monkeypatch):
    from app.core import users
    from app.core.config import get_settings

    _seed(db)
    users.crea_usuari(db, "altre", "bona", "docent", institucio_id="nou_patufet")
    db.commit()
    s = get_settings()
    monkeypatch.setattr(s, "login_max_intents", 2)

    mal = {"usuari": "victima", "contrasenya": "x", "institucio": "nou_patufet"}
    for _ in range(2):
        client.post("/api/auth/login", json=mal)
    # «victima» bloquejada…
    assert client.post("/api/auth/login", json={"usuari": "victima", "contrasenya": "bona", "institucio": "nou_patufet"}).status_code == 429
    # …però «altre» pot entrar amb normalitat.
    assert client.post("/api/auth/login", json={"usuari": "altre", "contrasenya": "bona", "institucio": "nou_patufet"}).status_code == 200
