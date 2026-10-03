"""Regressions de l'auditoria: dades sintètiques, SQLite i cap servei extern.

La identitat es comprova amb el guardià REAL; no s'usa l'acomodació de conftest.
"""
from __future__ import annotations

import datetime as dt

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from starlette.requests import Request

from app.core import documents_crypto, security
from app.core.config import Settings
from app.core.roles import Rol
from app.db.models import Chunk, Document, DocumentOriginal, Institucio, User

AUTENTICACIO_REAL = True


@pytest.fixture(autouse=True)
def _clau_originals_sintetica(monkeypatch):
    monkeypatch.setattr(documents_crypto, "keyring",
                        lambda: ("audit-test-v1", {"audit-test-v1": b"T" * 32}))


def _settings(**kwargs):
    return Settings(_env_file=None, jwt_secret="audit-synthetic-key-for-tests-only-20261001",
                    acces_remot_admin_only=False, proxy_de_confianca=False, **kwargs)


def _request(ip="127.0.0.1"):
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [],
                    "client": (ip, 1234), "server": ("testserver", 80), "scheme": "http"})


def _user(db, username="audit", rol=Rol.DIRECCIO, institucio="nou_patufet"):
    u = User(username=username, password_hash="no-login-in-this-test", rol=rol.value,
             institucio_id=institucio, actiu=True, token_version=0)
    db.add(u)
    db.commit()
    return u


def _h(username="audit", rol=Rol.DIRECCIO, inst="nou_patufet"):
    return {"Authorization": "Bearer " + security.crea_token(username, rol, institucio=inst)}


def _guard(monkeypatch, SessionLocal, s, rol=Rol.DIRECCIO, ip="127.0.0.1"):
    import app.db.session as sessions
    monkeypatch.setattr(sessions, "get_sessionmaker", lambda: SessionLocal)
    token = security.crea_token("audit", rol, settings=s)
    return security.get_current_user(_request(ip), "Bearer " + token, s)


def test_compte_inexistent_rebutjat_inclus_en_dev(monkeypatch, SessionLocal):
    with pytest.raises(HTTPException) as exc:
        _guard(monkeypatch, SessionLocal, _settings(entorn="dev"))
    assert exc.value.status_code == 401


def test_esborrar_compte_revoca_token_immediat(monkeypatch, SessionLocal, db):
    row = _user(db)
    s = _settings()
    assert _guard(monkeypatch, SessionLocal, s).usuari == "audit"
    db.delete(row)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        _guard(monkeypatch, SessionLocal, s)
    assert exc.value.status_code == 401


def test_error_obrint_bd_no_accepta_jwt(monkeypatch):
    import app.db.session as sessions

    def _fail():
        raise RuntimeError("synthetic-db-unavailable")

    monkeypatch.setattr(sessions, "get_sessionmaker", _fail)
    s = _settings()
    token = security.crea_token("audit", Rol.DIRECCIO, settings=s)
    with pytest.raises(HTTPException) as exc:
        security.get_current_user(_request(), "Bearer " + token, s)
    assert exc.value.status_code == 503
    assert "synthetic-db" not in exc.value.detail


def test_error_consulta_bd_no_accepta_jwt(monkeypatch):
    import app.db.session as sessions

    class Broken:
        closed = False

        def scalar(self, query):
            raise RuntimeError("synthetic-query-unavailable")

        def close(self):
            self.closed = True

    db = Broken()
    monkeypatch.setattr(sessions, "get_sessionmaker", lambda: lambda: db)
    s = _settings()
    token = security.crea_token("audit", Rol.DIRECCIO, settings=s)
    with pytest.raises(HTTPException) as exc:
        security.get_current_user(_request(), "Bearer " + token, s)
    assert exc.value.status_code == 503 and db.closed


def test_degradacio_rol_aplica_control_remot(monkeypatch, SessionLocal, db):
    _user(db, rol=Rol.DOCENT)
    s = _settings()
    s.acces_remot_admin_only = True
    with pytest.raises(HTTPException) as exc:
        _guard(monkeypatch, SessionLocal, s, rol=Rol.DIRECCIO, ip="203.0.113.42")
    assert exc.value.status_code == 403


def test_error_politica_ip_tanca_acces(monkeypatch, SessionLocal, db):
    from app.core import acces_xarxa
    _user(db, rol=Rol.DOCENT)

    def _fail(*a, **k):
        raise RuntimeError("synthetic-policy-unavailable")

    monkeypatch.setattr(acces_xarxa, "politica_per_institucio", _fail)
    with pytest.raises(HTTPException) as exc:
        _guard(monkeypatch, SessionLocal, _settings(), rol=Rol.DOCENT)
    assert exc.value.status_code == 503


def test_rol_bd_invalid_rebutjat(monkeypatch, SessionLocal, db):
    row = _user(db)
    row.rol = "invalid"
    db.commit()
    with pytest.raises(HTTPException) as exc:
        _guard(monkeypatch, SessionLocal, _settings())
    assert exc.value.status_code == 401


@pytest.mark.parametrize("camp", ["exp", "iat", "inst", "tv"])
def test_jwt_sense_claim_obligatori_rebutjat(camp):
    s = _settings()
    ara = dt.datetime.now(dt.timezone.utc)
    p = {"sub": "audit", "rol": "direccio", "inst": "nou_patufet", "tv": 0,
         "iss": "adeptify", "aud": "adeptify", "iat": ara, "exp": ara + dt.timedelta(minutes=5)}
    p.pop(camp)
    token = jwt.encode(p, s.jwt_secret, algorithm=s.jwt_algorithm)
    with pytest.raises(HTTPException) as exc:
        security.descodifica_token(token, s)
    assert exc.value.status_code == 401


@pytest.mark.parametrize("camp,valor", [("tv", "bad"), ("tv", -1), ("tv", True),
                                        ("inst", []), ("rol", {}), ("sub", 12)])
def test_claim_malformat_retorna_401(camp, valor):
    s = _settings()
    ara = dt.datetime.now(dt.timezone.utc)
    p = {"sub": "audit", "rol": "direccio", "inst": "nou_patufet", "tv": 0,
         "iss": "adeptify", "aud": "adeptify", "iat": ara, "exp": ara + dt.timedelta(minutes=5)}
    p[camp] = valor
    with pytest.raises(HTTPException) as exc:
        security.descodifica_token(jwt.encode(p, s.jwt_secret, algorithm=s.jwt_algorithm), s)
    assert exc.value.status_code == 401


@pytest.mark.parametrize("rol", [Rol.FAMILIA, Rol.ALUMNE])
def test_familia_alumne_no_esborren_documents(client, db, rol):
    _user(db, rol=rol)
    doc = Document(doc_id="audit_doc", filename="generic.md", tipus="md", visibilitat="tots")
    db.add(doc)
    db.commit()
    assert client.delete("/api/documents/audit_doc", headers=_h(rol=rol)).status_code == 403
    db.expire_all()
    assert db.get(Document, doc.id) is not None


def test_docent_no_esborra_original_admin(client, db):
    _user(db, rol=Rol.DOCENT)
    doc = Document(doc_id="audit_admin", filename="restricted.md", tipus="md", visibilitat="admin")
    db.add(doc)
    db.commit()
    assert client.delete("/api/documents/audit_admin", headers=_h(rol=Rol.DOCENT)).status_code == 403
    db.expire_all()
    assert db.get(Document, doc.id) is not None


def test_metadades_admin_i_sensibles_no_surten_a_familia(client, db):
    _user(db, rol=Rol.FAMILIA)
    db.add(Institucio(slug="nou_patufet", nom="Synthetic audit centre", actiu=True))
    db.add_all([Document(doc_id="admin", filename="restricted.md", tipus="md", visibilitat="admin"),
                Document(doc_id="legacy_sensitive", filename="legacy.md", tipus="md",
                         visibilitat="tots", sensibilitat="sensible")])
    db.commit()
    r = client.get("/api/documents", headers=_h(rol=Rol.FAMILIA))
    assert r.status_code == 200 and r.json()["documents"] == []
    assert client.get("/api/documents/legacy_sensitive/descarrega",
                      headers=_h(rol=Rol.FAMILIA)).status_code == 403


def test_ingesta_homonima_no_canvia_centre_ni_original(db, tmp_path):
    from app.ingest import pipeline
    f = tmp_path / "generic.md"
    f.write_text("Contingut sintètic del centre A.", encoding="utf-8")
    assert pipeline.ingesta_fitxer(db, f, institucio_id="audit_a")[0] == 1
    f.write_text("Contingut sintètic del centre B.", encoding="utf-8")
    assert pipeline.ingesta_fitxer(db, f, institucio_id="audit_b")[0] == 1
    docs = db.scalars(select(Document).order_by(Document.institucio_id)).all()
    assert len(docs) == 2 and len({d.doc_id for d in docs}) == 2
    for doc, suffix in zip(docs, ("centre A.", "centre B.")):
        original = db.get(DocumentOriginal, doc.doc_id)
        assert documents_crypto.reveal(original, doc.institucio_id, doc.doc_id).decode().endswith(suffix)
    assert pipeline.elimina_document(db, docs[0].doc_id, institucio_id="audit_b") is False
    assert db.get(Document, docs[0].id) is not None


@pytest.mark.parametrize(("sensibilitat", "origen"), [
    (None, "document"), ("public", "document"), ("intern", "document"),
    ("docent", "moodle_backup"),
])
def test_ingesta_medica_no_crea_chunks_ni_embeddings(
    db, tmp_path, monkeypatch, sensibilitat, origen
):
    from app.ingest import pipeline
    from app.rag.embeddings import get_embedder

    def _prohibit(*a, **k):
        raise AssertionError("No s'ha d'embeddejar contingut sensible")

    monkeypatch.setattr(get_embedder(), "embed", _prohibit)
    f = tmp_path / "synthetic-medical.md"
    f.write_text("Asma i medicació: exemple sintètic per a l'auditoria.", encoding="utf-8")
    assert pipeline.ingesta_fitxer(
        db, f, sensibilitat=sensibilitat, origen=origen
    ) == (1, 0)
    doc = db.scalar(select(Document))
    assert doc.sensibilitat == "sensible" and doc.visibilitat == "admin"
    assert not doc.exportable_ia and doc.n_chunks == 0
    assert db.scalar(select(Chunk)) is None


@pytest.mark.parametrize("fallada", ["mida", "lectura"])
def test_reingesta_no_exposa_original_sensible_anterior(
    db, tmp_path, monkeypatch, fallada
):
    from pathlib import Path
    from app.ingest import pipeline

    f = tmp_path / "synthetic-version.md"
    f.write_text("Asma: exemple sintètic.", encoding="utf-8")
    assert pipeline.ingesta_fitxer(db, f) == (1, 0)
    doc = db.scalar(select(Document))
    doc_id = doc.doc_id
    assert db.get(DocumentOriginal, doc_id) is not None
    f.write_text("Horari públic de secretaria.", encoding="utf-8")
    if fallada == "mida":
        monkeypatch.setattr(pipeline, "_MAX_ORIGINAL_BYTES", 4)
    else:
        open_real = Path.open
        def _fallada_lectura(self, mode="r", *args, **kwargs):
            if self == f and mode == "rb":
                raise OSError("synthetic-read-failure")
            return open_real(self, mode, *args, **kwargs)
        monkeypatch.setattr(Path, "open", _fallada_lectura)
    assert pipeline.ingesta_fitxer(db, f)[1] > 0
    db.refresh(doc)
    assert doc.sensibilitat != "sensible" and doc.visibilitat == "tots"
    assert db.get(DocumentOriginal, doc_id) is None


def test_error_bd_original_desfa_canvi_permisos_i_chunks(db, tmp_path, monkeypatch):
    from app.ingest import pipeline

    f = tmp_path / "synthetic-version.md"
    anterior = "Asma: exemple sintètic."
    f.write_text(anterior, encoding="utf-8")
    pipeline.ingesta_fitxer(db, f)
    doc = db.scalar(select(Document))
    doc_id = doc.doc_id
    f.write_text("Horari públic de secretaria.", encoding="utf-8")
    get_real = db.get
    def _fallada_bd(model, *args, **kwargs):
        if model is DocumentOriginal:
            raise RuntimeError("synthetic-original-db-failure")
        return get_real(model, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(db, "get", _fallada_bd)
        with pytest.raises(RuntimeError):
            pipeline.ingesta_fitxer(db, f)
    db.refresh(doc)
    assert doc.sensibilitat == "sensible" and doc.visibilitat == "admin"
    assert doc.n_chunks == 0 and db.scalar(select(Chunk)) is None
    original = db.get(DocumentOriginal, doc_id)
    assert original.contingut != anterior.encode()
    assert documents_crypto.reveal(original, doc.institucio_id, doc_id).decode() == anterior


def test_api_ingesta_sensible_avisa_sense_error_ocr(client, db):
    _user(db)
    r = client.post("/api/ingest", headers=_h(), files={
        "fitxer": ("synthetic-medical.md", b"Asma: exemple sintetic.", "text/markdown")})
    assert r.status_code == 202
    assert r.json()["avis"] == "document_sensible"
    assert db.scalar(select(Chunk)) is None


@pytest.mark.parametrize("invalid_key", [False, True, "empty-id", "long-id"])
def test_api_ingesta_xifratge_no_disponible_tanca_sense_persistir(client, db, monkeypatch, invalid_key):
    _user(db)
    def _unavailable():
        if invalid_key in {"empty-id", "long-id"}:
            active = "" if invalid_key == "empty-id" else "T" * 129
            return active, {active: b"T" * 32}
        if invalid_key:
            raise documents_crypto.OriginalNoDisponible("synthetic-private-config-error")
        return "missing", {}
    monkeypatch.setattr(documents_crypto, "keyring", _unavailable)
    response = client.post("/api/ingest", headers=_h(), files={
        "fitxer": ("synthetic-medical.md", b"Asma: exemple sintetic.", "text/markdown")})
    assert response.status_code == 503
    assert response.json()["error"]["missatge"] == "No es pot protegir l'original del document."
    assert db.scalar(select(Document)) is None
    assert db.scalar(select(DocumentOriginal)) is None
    assert db.scalar(select(Chunk)) is None


def test_error_dlp_no_persisteix_coneixement(db, tmp_path, monkeypatch):
    from app.ingest import pipeline
    from app.security import content_safety

    def _fail(*a, **k):
        raise RuntimeError("synthetic-dlp-failure")

    monkeypatch.setattr(content_safety, "classifica_textos", _fail)
    f = tmp_path / "generic.md"
    f.write_text("Contingut sintètic.", encoding="utf-8")
    with pytest.raises(ValueError):
        pipeline.ingesta_fitxer(db, f)
    assert db.scalar(select(Document)) is None and db.scalar(select(Chunk)) is None


def test_retrieval_i_mcp_no_llegeixen_sensibles_antics(db):
    from app.mcp.tools import _cerca_documents
    from app.rag.embeddings import get_embedder
    from app.rag.retriever import retrieve
    doc = Document(doc_id="legacy_sensitive", filename="legacy.md", tipus="md",
                   visibilitat="tots", sensibilitat="sensible")
    db.add(doc)
    db.flush()
    db.add(Chunk(document_id=doc.id, contingut="Dades sintètiques sensibles.", ordre=0,
                 embedding=get_embedder().embed(["Dades sintètiques sensibles."])[0]))
    db.commit()
    assert retrieve(db, "Dades", institucio_id="nou_patufet", incloure_admin=True) == []
    assert retrieve(db, "Dades", institucio_id=None) == []
    res = _cerca_documents(db, "Dades", institucio_id="nou_patufet")
    assert res.ok and res.contingut == []
    assert _cerca_documents(db, "Dades").ok is False


def test_feedback_nomes_del_propietari_i_centre(client, db):
    from app.db.models import Conversation, Feedback, Message
    _user(db)
    ids = []
    for username, inst in [("audit", "nou_patufet"), ("other", "nou_patufet"), ("audit", "audit_b")]:
        conv = Conversation(agent_id="secretaria", usuari=username, rol="direccio", institucio_id=inst)
        db.add(conv)
        db.flush()
        msg = Message(conversation_id=conv.id, rol="assistant", contingut="Resposta sintètica.")
        db.add(msg)
        db.flush()
        ids.append(msg.id)
    db.commit()
    for message_id in ids[1:] + ["unknown"]:
        r = client.post("/api/feedback", headers=_h(), json={"message_id": message_id, "valor": "util"})
        assert r.status_code == 404
    assert db.scalar(select(Feedback)) is None
    assert client.post("/api/feedback", headers=_h(),
                       json={"message_id": ids[0], "valor": "util"}).status_code == 204
    assert len(db.scalars(select(Feedback)).all()) == 1


def test_wrappers_model_no_activen_codi_remot(monkeypatch):
    """Comprova la frontera amb FlagEmbedding sense carregar ni descarregar models."""
    import sys
    from types import SimpleNamespace
    from app.rag import device
    from app.rag.embeddings import BGEEmbedder
    from app.rag.rerank import BGEReranker
    crides = []

    def _model(name, **kwargs):
        crides.append(kwargs)
        return object()

    monkeypatch.setitem(sys.modules, "FlagEmbedding",
                        SimpleNamespace(BGEM3FlagModel=_model, FlagReranker=_model))
    monkeypatch.setattr(device, "resol_device", lambda name: "cpu")
    BGEEmbedder()._carrega()
    BGEReranker()._carrega()
    assert len(crides) == 2 and all(k["trust_remote_code"] is False for k in crides)
