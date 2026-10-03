"""Llistat/descàrrega coherents amb el perímetre públic familiar i d'alumnat."""
import base64
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api import routes_documents
from app.core import documents_crypto, users
from app.core.roles import Rol
from app.core.security import Usuari, crea_token
from app.db.models import Document, DocumentOriginal, Institucio

AUTENTICACIO_REAL = True


@pytest.fixture(autouse=True)
def synthetic_key(monkeypatch):
    config = SimpleNamespace(documents_data_key=base64.b64encode(b"T" * 32).decode(),
        documents_data_key_id="public-doc-tests", documents_data_keys="{}",
        documents_allow_legacy_sensitive=False, es_prod=False)
    monkeypatch.setattr(documents_crypto, "get_settings", lambda: config)


def _doc(db, doc_id, tenant="public_a", sensitivity="public", visibility="tots"):
    doc = Document(doc_id=doc_id, institucio_id=tenant, filename=doc_id + ".md",
        tipus="md", sensibilitat=sensitivity, visibilitat=visibility)
    blob, fmt = documents_crypto.protect(b"synthetic public education document", tenant, doc_id, required=True)
    db.add(doc)
    db.add(DocumentOriginal(doc_id=doc_id, institucio_id=tenant, filename=doc_id + ".md",
        mime="text/markdown", mida=35, contingut=blob, contingut_format=fmt))
    return doc


def _seed(db, role=Rol.FAMILIA):
    db.add_all([Institucio(slug="public_a", nom="Synthetic A", actiu=True),
                Institucio(slug="public_b", nom="Synthetic B", actiu=True)])
    users.crea_usuari(db, "synthetic_reader", "synthetic-password", role.value, institucio_id="public_a")
    db.commit()
    return {"Authorization": f"Bearer {crea_token('synthetic_reader', role, institucio='public_a')}"}


@pytest.mark.parametrize("role", [Rol.FAMILIA, Rol.ALUMNE])
def test_family_student_only_explicit_public_tenant_documents(client, db, role):
    headers = _seed(db, role)
    _doc(db, "public_a:allowed")
    for level in ("intern", "docent", "sensible", "unknown"):
        _doc(db, "public_a:" + level, sensitivity=level)
    _doc(db, "public_a:admin", visibility="admin")
    _doc(db, "public_b:other", tenant="public_b")
    db.commit()
    response = client.get("/api/documents?vis=tots&sensibilitat=public", headers=headers)
    assert response.status_code == 200, response.text
    assert [doc["doc_id"] for doc in response.json()["documents"]] == ["public_a:allowed"]
    assert client.get("/api/documents/public_a:allowed/descarrega", headers=headers).content == b"synthetic public education document"
    for name in ("intern", "docent", "sensible", "unknown", "admin"):
        assert client.get("/api/documents/public_a:" + name + "/descarrega?vis=tots", headers=headers).status_code == 403
    assert client.get("/api/documents/public_b:other/descarrega", headers=headers).status_code == 404


def test_reclassification_revokes_download_before_decryption(client, db, monkeypatch):
    headers = _seed(db)
    doc = _doc(db, "public_a:mutable")
    db.commit()
    assert client.get("/api/documents/public_a:mutable/descarrega", headers=headers).status_code == 200

    def forbidden_decryption(*args, **kwargs):
        pytest.fail("Restricted documents must be rejected before reading their contents.")

    monkeypatch.setattr(documents_crypto, "reveal", forbidden_decryption)
    for level, visibility in (("intern", "tots"), ("docent", "tots"), ("sensible", "tots"),
                              ("unknown", "tots"), ("public", "admin")):
        doc.sensibilitat, doc.visibilitat = level, visibility
        db.commit()
        assert client.get("/api/documents/public_a:mutable/descarrega?vis=tots", headers=headers).status_code == 403
        assert client.get("/api/documents", headers=headers).json()["documents"] == []


def test_empty_missing_inactive_tenant_denies_reads_before_decryption(db, monkeypatch):
    _seed(db)
    # Simula una fila de llegat mal formada, que tampoc autoritza una lectura.
    db.add(Document(doc_id="empty:doc", institucio_id="", filename="empty.md", tipus="md",
                    sensibilitat="public", visibilitat="tots"))
    db.add(DocumentOriginal(doc_id="empty:doc", institucio_id="", filename="empty.md",
        mime="text/markdown", mida=9, contingut=b"synthetic", contingut_format="plain"))
    _doc(db, "public_a:allowed")
    db.commit()
    monkeypatch.setattr(documents_crypto, "reveal", lambda *a, **kw: pytest.fail("Tenant must be verified first."))
    for tenant in ("", "   ", "missing"):
        user = Usuari("synthetic_reader", Rol.FAMILIA, tenant)
        with pytest.raises(HTTPException) as listing:
            routes_documents.llista_documents(user, db)
        assert listing.value.status_code == 403
        with pytest.raises(HTTPException) as download:
            routes_documents.descarrega_document("empty:doc", user, db)
        assert download.value.status_code == 403
    institution = db.scalar(select(Institucio).where(Institucio.slug == "public_a"))
    institution.actiu = False
    db.commit()
    user = Usuari("synthetic_reader", Rol.FAMILIA, "public_a")
    with pytest.raises(HTTPException) as download:
        routes_documents.descarrega_document("public_a:allowed", user, db)
    assert download.value.status_code == 403
