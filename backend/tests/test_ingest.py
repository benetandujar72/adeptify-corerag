"""Tests del pipeline d'ingesta (loaders, chunking, indexació) i endpoints."""

from __future__ import annotations

from pathlib import Path

from app.ingest import pipeline
from app.ingest.chunking import chunk_pagines
from app.ingest.loaders import Pagina, tipus_de


def test_tipus_de():
    assert tipus_de(Path("a.pdf")) == "pdf"
    assert tipus_de(Path("a.DOCX")) == "docx"
    assert tipus_de(Path("a.md")) == "md"
    assert tipus_de(Path("a.html")) == "html"
    assert tipus_de(Path("a.exe")) is None


def test_chunking_amb_solapament():
    text = "Paràgraf u. " * 100  # text llarg per forçar diversos chunks
    chunks = chunk_pagines([Pagina(text=text, pagina=3)], mida=200, solapament=40)
    assert len(chunks) > 1
    assert all(c.pagina == 3 for c in chunks)
    assert all(len(c.contingut) <= 260 for c in chunks)  # mida + solapament


def test_ingesta_carpeta(tmp_path, db):
    # Crea fitxers genèrics (no noms codificats) de diversos tipus.
    (tmp_path / "doc_a.md").write_text("# Títol\n\nContingut de prova A.", encoding="utf-8")
    (tmp_path / "doc_b.txt").write_text("Contingut de prova B més llarg." * 5, encoding="utf-8")
    sub = tmp_path / "subcarpeta"
    sub.mkdir()
    (sub / "doc_c.html").write_text("<html><body><p>Hola C</p></body></html>", encoding="utf-8")

    docs, chunks = pipeline.ingesta_carpeta(db, tmp_path)
    assert docs == 3
    assert chunks >= 3


def test_reingesta_actualitza_no_duplica(tmp_path, db):
    f = tmp_path / "doc.md"
    f.write_text("Versió inicial del document.", encoding="utf-8")
    docs1, _ = pipeline.ingesta_fitxer(db, f)
    assert docs1 == 1
    f.write_text("Versió actualitzada del document amb més text.", encoding="utf-8")
    docs2, _ = pipeline.ingesta_fitxer(db, f)
    assert docs2 == 0  # no es crea un document nou; es reindexa


def test_endpoint_ingest_path(client, auth, tmp_path, monkeypatch):
    # La ingesta de carpeta es conté dins de SAMPLE_DATA_PATH; per al test, fem
    # que la base sigui el tmp_path.
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "sample_data_path", str(tmp_path))
    (tmp_path / "nota.md").write_text("Nota de prova per ingerir.", encoding="utf-8")
    resp = client.post("/api/ingest", headers=auth, params={"path": str(tmp_path)})
    assert resp.status_code == 202
    cos = resp.json()
    assert "job_id" in cos
    # Consulta l'estat del job (la tasca de fons ja s'ha executat amb TestClient).
    estat = client.get(f"/api/ingest/{cos['job_id']}", headers=auth)
    assert estat.status_code == 200
    assert estat.json()["estat"] in {"fet", "processant", "encuat", "error"}


def test_endpoint_ingest_path_fora_de_base_denegat(client, auth, tmp_path, monkeypatch):
    """Travessa de directoris: una ruta FORA de la base permesa retorna 400."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "sample_data_path", str(tmp_path))
    resp = client.post("/api/ingest", headers=auth, params={"path": "/etc"})
    assert resp.status_code == 400


def test_endpoint_ingest_job_inexistent(client, auth):
    resp = client.get("/api/ingest/no-existeix", headers=auth)
    assert resp.status_code == 404
