"""Tests del control d'accés remot (Fase 1).

- Helper pur `_es_ip_local` (rang d'IP configurable).
- Enforcement a través de l'app: des de la xarxa local, tots els rols; des de
  fora (remot), només el rol d'administració (direcció/superadmin).
"""

from __future__ import annotations


def test_es_ip_local_rangs():
    from app.core.security import _es_ip_local

    cidrs = "192.168.0.0/16,10.0.0.0/8"
    assert _es_ip_local("192.168.1.50", cidrs) is True
    assert _es_ip_local("10.20.30.40", cidrs) is True
    assert _es_ip_local("8.8.8.8", cidrs) is False
    assert _es_ip_local("no-és-ip", cidrs) is False  # fail-closed
    assert _es_ip_local(None, cidrs) is False


def _crea_usuaris(db):
    from app.core import users

    users.crea_usuari(db, "dir_remot", "k", "direccio")
    users.crea_usuari(db, "doc_remot", "k", "docent")
    db.commit()


def test_acces_remot_admin_only(client, db, monkeypatch):
    from app.core.config import get_settings

    _crea_usuaris(db)
    # Login en LOCAL (control desactivat per defecte als tests) → ambdós obtenen token.
    tok_dir = client.post("/api/auth/login", json={"usuari": "dir_remot", "contrasenya": "k"}).json()["token"]
    tok_doc = client.post("/api/auth/login", json={"usuari": "doc_remot", "contrasenya": "k"}).json()["token"]

    # Activem el control i fem que les peticions semblin remotes via X-Forwarded-For.
    s = get_settings()
    monkeypatch.setattr(s, "acces_remot_admin_only", True)
    monkeypatch.setattr(s, "proxy_de_confianca", True)
    monkeypatch.setattr(s, "xarxa_local_cidrs", "192.168.0.0/16")

    remot = {"X-Forwarded-For": "8.8.8.8"}  # fora de l'allow-list → remot
    local = {"X-Forwarded-For": "192.168.1.50"}  # dins l'allow-list → local

    # Remot: direcció OK, docent 403.
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok_dir}", **remot}).status_code == 200
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok_doc}", **remot}).status_code == 403

    # Local: el docent també hi pot accedir.
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok_doc}", **local}).status_code == 200


def test_login_remot_no_admin_denegat(client, db, monkeypatch):
    from app.core.config import get_settings

    _crea_usuaris(db)
    s = get_settings()
    monkeypatch.setattr(s, "acces_remot_admin_only", True)
    monkeypatch.setattr(s, "proxy_de_confianca", True)
    monkeypatch.setattr(s, "xarxa_local_cidrs", "192.168.0.0/16")
    remot = {"X-Forwarded-For": "203.0.113.7"}

    # El docent NO pot ni fer login de forma remota (no s'emet token).
    r_doc = client.post("/api/auth/login", json={"usuari": "doc_remot", "contrasenya": "k"}, headers=remot)
    assert r_doc.status_code == 403
    # La direcció sí.
    r_dir = client.post("/api/auth/login", json={"usuari": "dir_remot", "contrasenya": "k"}, headers=remot)
    assert r_dir.status_code == 200
