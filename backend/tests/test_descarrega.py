"""Tests de la descàrrega del document original citat (F1, docs/20).

Verifica: es desa l'original a la ingesta, es pot descarregar, aïllament entre
institucions (cross-tenant → 404) i respecte de la visibilitat "admin".
"""

from __future__ import annotations

import base64
import pytest


@pytest.fixture(autouse=True)
def _clau_originals_sintetica(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "documents_data_key", base64.b64encode(b"T" * 32).decode())
    monkeypatch.setattr(get_settings(), "documents_data_key_id", "download-test-v1")


def _login(client, u, inst):
    return client.post(
        "/api/auth/login", json={"usuari": u, "contrasenya": "k", "institucio": inst}
    ).json()["token"]


def _ingereix(db, tmp_path, nom, text, institucio, visibilitat="tots"):
    from app.ingest import pipeline

    f = tmp_path / nom
    f.write_text(text, encoding="utf-8")
    pipeline.ingesta_fitxer(db, f, institucio_id=institucio, visibilitat=visibilitat)


def test_descarrega_original_i_aillament(client, db, tmp_path):
    from app.core import users

    users.crea_usuari(db, "dir_a", "k", "direccio", institucio_id="inst_a")
    users.crea_usuari(db, "dir_b", "k", "direccio", institucio_id="inst_b")
    db.commit()
    _ingereix(db, tmp_path, "nota.md", "Contingut de prova per a la nota del centre A.", "inst_a")

    tok_a = _login(client, "dir_a", "inst_a")
    r = client.get("/api/documents/inst_a__nota/descarrega", headers={"Authorization": f"Bearer {tok_a}"})
    assert r.status_code == 200
    assert "Contingut de prova" in r.content.decode("utf-8")

    # Cross-tenant: la direcció d'inst_b NO hi accedeix (404, no revela existència).
    tok_b = _login(client, "dir_b", "inst_b")
    assert client.get(
        "/api/documents/inst_a__nota/descarrega", headers={"Authorization": f"Bearer {tok_b}"}
    ).status_code == 404


def test_descarrega_visibilitat_admin(client, db, tmp_path):
    from app.core import users

    users.crea_usuari(db, "dir_a", "k", "direccio", institucio_id="inst_a")
    users.crea_usuari(db, "doc_a", "k", "docent", institucio_id="inst_a")
    db.commit()
    _ingereix(db, tmp_path, "gestio.md", "Document de gestió intern.", "inst_a", visibilitat="admin")

    # La direcció (admin) sí; el docent no (403).
    tok_dir = _login(client, "dir_a", "inst_a")
    assert client.get(
        "/api/documents/inst_a__gestio/descarrega", headers={"Authorization": f"Bearer {tok_dir}"}
    ).status_code == 200
    tok_doc = _login(client, "doc_a", "inst_a")
    assert client.get(
        "/api/documents/inst_a__gestio/descarrega", headers={"Authorization": f"Bearer {tok_doc}"}
    ).status_code == 403


def test_descarrega_sense_original_404(client, db, document_indexat):
    """Un document indexat sense original desat (p. ex. anterior a F1) → 404 net."""
    from app.core import users

    # El fixture document_indexat insereix Document+Chunk directament (sense original)
    # a la institució per defecte 'nou_patufet'.
    users.crea_usuari(db, "dir_np", "k", "direccio", institucio_id="nou_patufet")
    db.commit()
    tok = _login(client, "dir_np", "nou_patufet")
    r = client.get(
        f"/api/documents/{document_indexat.doc_id}/descarrega",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 404
