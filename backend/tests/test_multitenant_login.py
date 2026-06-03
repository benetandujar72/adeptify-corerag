"""Tests d'aïllament multi-tenant: login per institució + admin per institució.

Garanteix (requisit innegociable): la institució es valida explícitament al login
i una direcció NOMÉS pot veure/gestionar els usuaris del SEU centre.
"""

from __future__ import annotations


def _seed(db):
    from app.core import users

    # Mateix username a dos centres (cas real: un `direccio` per institució).
    users.crea_usuari(db, "direccio", "ka", "direccio", institucio_id="inst_a")
    users.crea_usuari(db, "direccio", "kb", "direccio", institucio_id="inst_b")
    users.crea_usuari(db, "docent", "k", "docent", institucio_id="inst_a")
    users.crea_usuari(db, "only_b", "k", "docent", institucio_id="inst_b")
    db.commit()


def _login(client, usuari, contrasenya, institucio):
    return client.post(
        "/api/auth/login",
        json={"usuari": usuari, "contrasenya": contrasenya, "institucio": institucio},
    )


def test_login_scoped_per_institucio(client, db):
    _seed(db)
    # «direccio»/«ka» és vàlid a inst_a però NO a inst_b (allà la contrasenya és «kb»).
    assert _login(client, "direccio", "ka", "inst_a").status_code == 200
    assert _login(client, "direccio", "ka", "inst_b").status_code == 401
    assert _login(client, "direccio", "kb", "inst_b").status_code == 200


def test_admin_institucio_nomes_veu_el_seu_centre(client, db):
    _seed(db)
    tok = _login(client, "direccio", "ka", "inst_a").json()["token"]
    h = {"Authorization": f"Bearer {tok}"}

    r = client.get("/api/institucio/users", headers=h)
    assert r.status_code == 200
    usuaris = r.json()["users"]
    assert {u["institucio_id"] for u in usuaris} == {"inst_a"}
    assert "only_b" not in {u["username"] for u in usuaris}  # no veu inst_b


def test_admin_institucio_no_pot_tocar_altres_centres(client, db):
    _seed(db)
    tok = _login(client, "direccio", "ka", "inst_a").json()["token"]
    h = {"Authorization": f"Bearer {tok}"}

    # Editar/esborrar un usuari d'inst_b → 404 (no és al seu centre).
    assert client.put("/api/institucio/users/only_b", headers=h, json={"nom": "x"}).status_code == 404
    assert client.delete("/api/institucio/users/only_b", headers=h).status_code == 404


def test_admin_institucio_no_escalada_ni_fuga(client, db):
    _seed(db)
    tok = _login(client, "direccio", "ka", "inst_a").json()["token"]
    h = {"Authorization": f"Bearer {tok}"}

    # No pot crear un superadmin (escalada de privilegis).
    r_sa = client.post(
        "/api/institucio/users", headers=h,
        json={"username": "z", "contrasenya": "k", "rol": "superadmin"},
    )
    assert r_sa.status_code == 403

    # Encara que enviï institucio_id aliè, l'usuari es crea al SEU centre (inst_a).
    r_new = client.post(
        "/api/institucio/users", headers=h,
        json={"username": "nou", "contrasenya": "k", "rol": "docent", "institucio_id": "inst_b"},
    )
    assert r_new.status_code == 201
    assert r_new.json()["institucio_id"] == "inst_a"


def test_docent_no_pot_gestionar_usuaris(client, db):
    _seed(db)
    tok = _login(client, "docent", "k", "inst_a").json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/institucio/users", headers=h).status_code == 403


def test_institucions_publiques_per_a_la_pantalla_de_seleccio(client, db):
    from app.core import institucions

    institucions.crea(db, "inst_a", "Institut A")
    institucions.crea(db, "inst_b", "Institut B")
    db.commit()
    r = client.get("/api/auth/institucions")  # públic (sense auth)
    assert r.status_code == 200
    slugs = {i["slug"] for i in r.json()["institucions"]}
    assert {"inst_a", "inst_b"}.issubset(slugs)
    # No exposa `config` (només slug/nom/branding).
    assert all(set(i.keys()) <= {"slug", "nom", "branding"} for i in r.json()["institucions"])
