"""Originals Suite/Core: AES real, AAD, permisos i migració reversible sintètica."""
import base64
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text

from app.core import crypto_envelope, documents_crypto
from app.core.roles import Rol
from app.core.security import crea_token
from app.db.models import Document, DocumentOriginal
from app.ingest import pipeline
from scripts.migrate_originals_crypto import ensure_schema, migrate

KEY = b"A" * 32


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    config = SimpleNamespace(documents_data_key=base64.b64encode(KEY).decode(),
        documents_data_key_id="test-v1", documents_data_keys="{}",
        documents_allow_legacy_sensitive=False, es_prod=False)
    monkeypatch.setattr(documents_crypto, "get_settings", lambda: config)
    return config


def _original(data=b"synthetic medical original", tenant="a", doc_id="a:doc", encrypted=True):
    content, storage = documents_crypto.protect(data, tenant, doc_id, required=True) if encrypted else (data, "plain")
    return DocumentOriginal(doc_id=doc_id, institucio_id=tenant, filename="synthetic.md", mime="text/markdown",
                            mida=len(data), contingut=content, contingut_format=storage)


def _document(tenant="a", doc_id="a:doc", sensitive=True):
    return Document(doc_id=doc_id, institucio_id=tenant, filename="synthetic.md", tipus="md",
                    versio="1", verificat_el="2026-10-01", n_chunks=0, estat="indexat",
                    sensibilitat="sensible" if sensitive else "docent", visibilitat="admin" if sensitive else "tots")


def test_roundtrip_ciphertext_nonce_i_context():
    original = _original()
    assert b"medical" not in original.contingut
    assert documents_crypto.reveal(original, "a", "a:doc") == b"synthetic medical original"
    assert _original().contingut != original.contingut
    for tenant, doc_id, purpose in (("b", "a:doc", "document-original"),
                                   ("a", "another", "document-original"), ("a", "a:doc", "health")):
        with pytest.raises(Exception):
            crypto_envelope.open_envelope(original.contingut, keys={"test-v1": KEY}, tenant=tenant,
                                          record_id=doc_id, purpose=purpose)


def test_tamper_no_fallback_i_key_rotation(keys):
    original = _original()
    corrupted = bytearray(original.contingut)
    corrupted[-1] ^= 1
    original.contingut = bytes(corrupted)
    with pytest.raises(documents_crypto.OriginalNoDisponible):
        documents_crypto.reveal(original, "a", "a:doc")
    original = _original()
    keys.documents_data_key_id = "test-v2"
    keys.documents_data_key = base64.b64encode(b"B" * 32).decode()
    keys.documents_data_keys = json.dumps({"test-v1": base64.b64encode(KEY).decode()})
    assert documents_crypto.reveal(original, "a", "a:doc") == b"synthetic medical original"
    assert documents_crypto.reveal(_original(), "a", "a:doc") == b"synthetic medical original"
    keys.documents_data_keys = "{}"
    with pytest.raises(documents_crypto.OriginalNoDisponible):
        documents_crypto.reveal(original, "a", "a:doc")


def test_required_key_i_legacy_gate(keys):
    keys.documents_data_key = ""
    with pytest.raises(documents_crypto.OriginalNoDisponible):
        documents_crypto.protect(b"sensitive", "a", "d", required=True)
    assert documents_crypto.protect(b"public", "a", "d", required=False) == (b"public", "plain")
    legacy = _original(encrypted=False)
    keys.es_prod = True
    with pytest.raises(documents_crypto.OriginalNoDisponible):
        documents_crypto.reveal(legacy, "a", "a:doc", sensitive=True)
    assert documents_crypto.reveal(legacy, "a", "a:doc", sensitive=True, migration=True)
    keys.documents_allow_legacy_sensitive = True
    assert documents_crypto.reveal(legacy, "a", "a:doc", sensitive=True)


def test_pipeline_original_encrypted_i_rollback_sense_key(db, tmp_path, keys):
    path = tmp_path / "synthetic.md"
    path.write_bytes(b"private synthetic")
    pipeline._desa_original(db, "a:doc", "a", path, "md", sensible=True)
    db.commit()
    original = db.get(DocumentOriginal, "a:doc")
    assert original.contingut_format == documents_crypto.FORMAT
    previous = original.contingut
    keys.documents_data_key = ""
    path.write_bytes(b"new private synthetic")
    with pytest.raises(documents_crypto.OriginalNoDisponible):
        pipeline._desa_original(db, "a:doc", "a", path, "md", sensible=True)
    db.rollback()
    assert db.get(DocumentOriginal, "a:doc").contingut == previous


def test_download_authorized_original_i_tenant_denial(client, db):
    db.add_all([_document(), _original()])
    db.commit()
    headers = {"Authorization": f"Bearer {crea_token('synthetic_manager', Rol.PAS, institucio='a')}"}
    response = client.get("/api/documents/a:doc/descarrega", headers=headers)
    assert response.status_code == 200, response.text
    assert response.content == b"synthetic medical original"
    forbidden = {"Authorization": f"Bearer {crea_token('synthetic_teacher', Rol.DOCENT, institucio='a')}"}
    assert client.get("/api/documents/a:doc/descarrega", headers=forbidden).status_code == 403
    other = {"Authorization": f"Bearer {crea_token('other_manager', Rol.PAS, institucio='b')}"}
    assert client.get("/api/documents/a:doc/descarrega", headers=other).status_code == 404


def test_migration_dry_run_apply_idempotent_rollback_i_tenant(db, engine):
    db.add_all([_document(), _original(encrypted=False), _document("b", "b:doc"),
                _original(tenant="b", doc_id="b:doc", encrypted=False)])
    db.commit()
    with engine.begin() as conn:
        result = migrate(conn, tenant="a")
        assert result["would_change"] == 1 and result["changed"] == 0
    db.expire_all()
    assert db.get(DocumentOriginal, "a:doc").contingut_format == "plain"
    with engine.begin() as conn:
        assert migrate(conn, tenant="a", apply=True)["changed"] == 1
        assert migrate(conn, tenant="a", apply=True)["changed"] == 0
    db.expire_all()
    assert db.get(DocumentOriginal, "a:doc").contingut_format == documents_crypto.FORMAT
    assert db.get(DocumentOriginal, "b:doc").contingut_format == "plain"
    with engine.begin() as conn:
        assert migrate(conn, tenant="a", rollback=True)["changed"] == 0
        assert migrate(conn, tenant="a", rollback=True, apply=True)["changed"] == 1
    db.expire_all()
    assert db.get(DocumentOriginal, "a:doc").contingut == b"synthetic medical original"


def test_migration_erreur_mid_batch_atomic(db, engine):
    broken = _original(doc_id="a:z-corrupt")
    broken.contingut = broken.contingut[:-1]
    db.add_all([_document(), _original(encrypted=False), _document(doc_id="a:z-corrupt"), broken])
    db.commit()
    with pytest.raises(documents_crypto.OriginalNoDisponible):
        with engine.begin() as conn:
            migrate(conn, tenant="a", apply=True)
    db.expire_all()
    assert db.get(DocumentOriginal, "a:doc").contingut_format == "plain"


def test_additive_schema_dry_run_i_apply():
    from sqlalchemy import create_engine
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE document_originals (doc_id TEXT PRIMARY KEY, contingut BLOB)"))
        conn.execute(text("INSERT INTO document_originals VALUES ('legacy', :bytes)"), {"bytes": b"original"})
        assert ensure_schema(conn)["schema_pending"] is True
        assert ensure_schema(conn, apply=True)["schema_changed"] is True
        assert ensure_schema(conn)["schema_pending"] is False
        assert conn.execute(text("SELECT contingut, contingut_format FROM document_originals")).one() == (b"original", "plain")
    engine.dispose()


def test_cli_env_file_synthetic_dryrun_apply_rollback_no_secrets(tmp_path):
    import subprocess
    import sys
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    dsn = f"sqlite+pysqlite:///{(tmp_path / 'synthetic.db').as_posix()}"
    engine = create_engine(dsn)
    Document.__table__.create(engine)
    DocumentOriginal.__table__.create(engine)
    with Session(engine) as session:
        session.add_all([_document(), _original(encrypted=False)])
        session.commit()
    env_file = tmp_path / "synthetic.env"
    synthetic_key = base64.b64encode(KEY).decode()
    env_file.write_text(f"DATABASE_URL={dsn}\nDOCUMENTS_DATA_KEY={synthetic_key}\nDOCUMENTS_DATA_KEY_ID=test-v1\n", encoding="utf-8")
    def run(*flags):
        result = subprocess.run([sys.executable, "-m", "scripts.migrate_originals_crypto", "--env-file",
            str(env_file), "--tenant", "a", "--include-all", *flags], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert synthetic_key not in result.stdout + result.stderr and dsn not in result.stdout + result.stderr
        return json.loads(result.stdout)
    assert run()["changed"] == 0
    assert run("--apply", "--ack-backup-restored")["changed"] == 1
    assert run("--rollback")["would_change"] == 1
    assert run("--rollback", "--apply", "--ack-backup-restored")["changed"] == 1
    with Session(engine) as session:
        assert session.get(DocumentOriginal, "a:doc").contingut == b"synthetic medical original"
    engine.dispose()
