"""Tests de la política d'accés per IP/CIDR per institució.

Cobertura:
- RBAC dels endpoints (només direcció/superadmin gestionen).
- Aïllament multi-tenant (una direcció NO veu/toca la d'una altra).
- Validació de CIDRs (entrades invàlides → 400).
- Detecció de CIDR a partir de la IP del peticionari.
- Safeguard: activar la política sense incloure la teva IP → 400.
- Lògica de `ip_permesa` i `proposa_cidr_lan` (unitari).
"""

from __future__ import annotations


def _login(client, u, inst):
    return client.post(
        "/api/auth/login", json={"usuari": u, "contrasenya": "k", "institucio": inst}
    ).json()["token"]


def _seed_centres(db):
    from app.core import users
    from app.db.models import Institucio

    db.add(Institucio(slug="inst_a", nom="Escola A", actiu=True))
    db.add(Institucio(slug="inst_b", nom="Escola B", actiu=True))
    users.crea_usuari(db, "dir_a", "k", "direccio", institucio_id="inst_a")
    users.crea_usuari(db, "dir_b", "k", "direccio", institucio_id="inst_b")
    users.crea_usuari(db, "doc_a", "k", "docent", institucio_id="inst_a")
    users.crea_usuari(db, "pas_a", "k", "pas", institucio_id="inst_a")
    users.crea_usuari(db, "fam_a", "k", "familia", institucio_id="inst_a")
    db.commit()


# ───────────────────────── Unitaris (sense HTTP) ────────────────────────────


def test_ip_permesa_politica_inactiva_permet_tot():
    from app.core.acces_xarxa import buida, ip_permesa
    p = buida()
    assert ip_permesa("8.8.8.8", p) is True
    assert ip_permesa(None, p) is True


def test_ip_permesa_match_cidr_lan():
    from app.core.acces_xarxa import ip_permesa
    p = {"actiu": True, "cidrs_lan": ["192.168.1.0/24"], "ips_permeses": []}
    assert ip_permesa("192.168.1.50", p) is True
    assert ip_permesa("10.0.0.1", p) is False


def test_ip_permesa_match_white_list():
    from app.core.acces_xarxa import ip_permesa
    p = {"actiu": True, "cidrs_lan": [], "ips_permeses": ["80.34.21.5"]}
    assert ip_permesa("80.34.21.5", p) is True
    assert ip_permesa("80.34.21.6", p) is False


def test_ip_permesa_ip_invalida_bloqueja():
    from app.core.acces_xarxa import ip_permesa
    p = {"actiu": True, "cidrs_lan": ["192.168.1.0/24"], "ips_permeses": []}
    assert ip_permesa("no-ip", p) is False


def test_proposa_cidr_lan_privada_ipv4():
    from app.core.acces_xarxa import proposa_cidr_lan
    assert proposa_cidr_lan("192.168.1.50") == "192.168.1.0/24"
    assert proposa_cidr_lan("10.20.30.40") == "10.20.30.0/24"


def test_proposa_cidr_lan_publica_retorna_none():
    from app.core.acces_xarxa import proposa_cidr_lan
    assert proposa_cidr_lan("8.8.8.8") is None
    assert proposa_cidr_lan(None) is None


def test_valida_entrades():
    from app.core.acces_xarxa import valida_entrades
    valides, invalides = valida_entrades(["192.168.1.0/24", "no-ip", "10.0.0.1", "999.0.0.0/8"])
    assert "192.168.1.0/24" in valides
    assert "10.0.0.1" in valides
    assert "no-ip" in invalides
    assert "999.0.0.0/8" in invalides


# ───────────────────────── Endpoints — RBAC ─────────────────────────────────


def test_get_xarxa_docent_403(client, db):
    _seed_centres(db)
    tok = _login(client, "doc_a", "inst_a")
    r = client.get("/api/institucio/seguretat/xarxa", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


def test_get_xarxa_pas_403(client, db):
    _seed_centres(db)
    tok = _login(client, "pas_a", "inst_a")
    r = client.get("/api/institucio/seguretat/xarxa", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


def test_get_xarxa_familia_403(client, db):
    _seed_centres(db)
    tok = _login(client, "fam_a", "inst_a")
    r = client.get("/api/institucio/seguretat/xarxa", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


def test_get_xarxa_direccio_200(client, db):
    _seed_centres(db)
    tok = _login(client, "dir_a", "inst_a")
    r = client.get("/api/institucio/seguretat/xarxa", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    d = r.json()
    assert d["actiu"] is False  # per defecte, política inactiva
    assert d["cidrs_lan"] == []
    assert d["ips_permeses"] == []


def test_put_xarxa_direccio_actualitza(client, db):
    _seed_centres(db)
    tok = _login(client, "dir_a", "inst_a")
    # Inclou la IP del TestClient (127.0.0.1) a la white-list per no auto-bloquejar-se.
    r = client.put(
        "/api/institucio/seguretat/xarxa",
        headers={"Authorization": f"Bearer {tok}"},
        json={"actiu": True, "cidrs_lan": ["192.168.1.0/24"], "ips_permeses": ["127.0.0.1"]},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["actiu"] is True
    assert "192.168.1.0/24" in d["cidrs_lan"]
    assert "127.0.0.1" in d["ips_permeses"]
    assert d["actualitzat_per"] == "dir_a"


def test_put_xarxa_cidr_invalid_400(client, db):
    _seed_centres(db)
    tok = _login(client, "dir_a", "inst_a")
    r = client.put(
        "/api/institucio/seguretat/xarxa",
        headers={"Authorization": f"Bearer {tok}"},
        json={"cidrs_lan": ["192.168.1.0/24", "no-és-un-cidr"], "ips_permeses": []},
    )
    assert r.status_code == 400


def test_put_xarxa_safeguard_no_auto_bloqueig(client, db):
    """Si la direcció activa la política sense incloure la seva IP, → 400."""
    _seed_centres(db)
    tok = _login(client, "dir_a", "inst_a")
    r = client.put(
        "/api/institucio/seguretat/xarxa",
        headers={"Authorization": f"Bearer {tok}"},
        # 127.0.0.1 NO és a aquest rang → l'admin quedaria fora.
        json={"actiu": True, "cidrs_lan": ["10.0.0.0/24"], "ips_permeses": []},
    )
    assert r.status_code == 400
    assert "bloquejat" in r.text.lower() or "rang" in r.text.lower()


def test_detecta_xarxa_direccio(client, db):
    _seed_centres(db)
    tok = _login(client, "dir_a", "inst_a")
    r = client.get(
        "/api/institucio/seguretat/xarxa/detecta",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    d = r.json()
    # El TestClient connecta com a 127.0.0.1 → és local → suggereix un CIDR.
    assert d["ip_actual"] == "127.0.0.1"
    assert d["es_local"] is True
    assert d["cidr_suggerit"] is not None


def test_aillament_cross_tenant(client, db):
    """La direcció d'inst_b veu la SEVA política, no la d'inst_a."""
    _seed_centres(db)
    # Direcció de inst_a defineix la seva política.
    tok_a = _login(client, "dir_a", "inst_a")
    client.put(
        "/api/institucio/seguretat/xarxa",
        headers={"Authorization": f"Bearer {tok_a}"},
        json={"actiu": True, "cidrs_lan": ["192.168.1.0/24"], "ips_permeses": ["127.0.0.1"]},
    )
    # Direcció d'inst_b llegeix la SEVA (ha de ser buida).
    tok_b = _login(client, "dir_b", "inst_b")
    r = client.get(
        "/api/institucio/seguretat/xarxa",
        headers={"Authorization": f"Bearer {tok_b}"},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["actiu"] is False
    assert d["cidrs_lan"] == []


def test_auditoria_acces_xarxa_update(client, db):
    _seed_centres(db)
    tok = _login(client, "dir_a", "inst_a")
    client.put(
        "/api/institucio/seguretat/xarxa",
        headers={"Authorization": f"Bearer {tok}"},
        json={"actiu": True, "cidrs_lan": [], "ips_permeses": ["127.0.0.1"]},
    )
    from app.db.models import AuditLog
    logs = db.query(AuditLog).filter(AuditLog.accio == "acces_xarxa_update").all()
    assert logs
    assert logs[-1].usuari == "dir_a"


# ───────────────────────── Política activa: enforcing ─────────────────────


def test_politica_activa_bloqueja_no_admin(client, db):
    """Si la política està activa i la IP del docent NO encaixa → 403 a qualsevol
    endpoint. La direcció (rol admin) NO es bloqueja per aquesta política."""
    _seed_centres(db)
    tok_dir = _login(client, "dir_a", "inst_a")
    # Activa amb un CIDR QUE NO inclou 127.0.0.1 (testclient) i hi posa la
    # IP del propi admin a la white-list per poder desar-ho.
    r = client.put(
        "/api/institucio/seguretat/xarxa",
        headers={"Authorization": f"Bearer {tok_dir}"},
        # Una xarxa LAN del centre fictícia + la white-list inclou la del TestClient
        # només per al moment de desar.
        json={"actiu": True, "cidrs_lan": ["192.168.99.0/24"], "ips_permeses": ["127.0.0.1"]},
    )
    assert r.status_code == 200, r.text
    # Ara retirem la white-list. Per fer-ho, la pròpia direcció ha de sobreviure
    # (per by-pass de rol admin), però amb una política on 127.0.0.1 NO encaixa
    # un docent QUE accedeix des de 127.0.0.1 ha de rebre 403.
    r2 = client.put(
        "/api/institucio/seguretat/xarxa",
        headers={"Authorization": f"Bearer {tok_dir}"},
        json={"actiu": True, "cidrs_lan": ["192.168.99.0/24"], "ips_permeses": []},
    )
    # Aquesta resposta el safeguard la marca com a 400 (admin queda fora). Però
    # com que el rol admin té BY-PASS al runtime, el safeguard NO es desactiva:
    # tot i així no podem desar-la. Per simular la situació la creem directament
    # a la BD.
    from app.core import acces_xarxa as ax
    from app.core import institucions

    inst = institucions.obte(db, "inst_a")
    inst.config = ax.fusiona(
        inst.config, actiu=True, cidrs_lan=["192.168.99.0/24"], ips_permeses=[],
        actualitzat_per="dir_a",
    )
    db.commit()
    ax.invalida_cache("inst_a")

    # Ara el docent (no admin) ha de rebre 403 a /api/agents.
    tok_doc = _login(client, "doc_a", "inst_a")
    r3 = client.get("/api/agents", headers={"Authorization": f"Bearer {tok_doc}"})
    assert r3.status_code == 403
    # La direcció (rol admin) segueix entrant.
    r4 = client.get("/api/agents", headers={"Authorization": f"Bearer {tok_dir}"})
    assert r4.status_code == 200


def test_politica_activa_white_list_permet(client, db):
    """Amb la IP del peticionari a la white-list, el docent passa."""
    _seed_centres(db)
    from app.core import acces_xarxa as ax
    from app.core import institucions

    inst = institucions.obte(db, "inst_a")
    inst.config = ax.fusiona(
        inst.config, actiu=True, cidrs_lan=["192.168.99.0/24"],
        ips_permeses=["127.0.0.1"], actualitzat_per="dir_a",
    )
    db.commit()
    ax.invalida_cache("inst_a")

    tok_doc = _login(client, "doc_a", "inst_a")
    r = client.get("/api/agents", headers={"Authorization": f"Bearer {tok_doc}"})
    assert r.status_code == 200
