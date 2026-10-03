"""Ingesta de multipart: límit de lectura abans de materialitzar/processar bytes."""
import asyncio

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.api import routes_documents
from app.core.roles import Rol
from app.core.security import Usuari


def test_ingest_upload_bounded_before_pipeline(db, monkeypatch):
    class SyntheticUpload:
        filename = "synthetic.md"
        size = None
        read_size = None

        async def read(self, size=-1):
            self.read_size = size
            assert size == 11
            return b"x" * 11

    upload = SyntheticUpload()
    monkeypatch.setattr(routes_documents, "MAX_UPLOAD_BYTES", 10)
    monkeypatch.setattr(routes_documents.pipeline, "ingesta_fitxer",
                        lambda *a, **kw: pytest.fail("Oversized upload must not reach ingestion."))
    with pytest.raises(HTTPException) as result:
        asyncio.run(routes_documents.ingest(BackgroundTasks(), upload, None,
                                           Usuari("synthetic_manager", Rol.PAS, "synthetic"), db))
    assert result.value.status_code == 413 and upload.read_size == 11
