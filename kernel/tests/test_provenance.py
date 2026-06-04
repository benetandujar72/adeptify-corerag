"""K8.4 — procedència anti-enverinament del RAG."""

from __future__ import annotations

from app.provenance import ProvenanceRegistry, filter_valid_chunks


def test_registre_i_validacio():
    reg = ProvenanceRegistry()
    reg.register(chunk_id="c1", source_id="doc:nofc", content="contingut original")
    assert reg.is_valid(chunk_id="c1", content="contingut original") is True
    # Contingut alterat (enverinat) → invàlid.
    assert reg.is_valid(chunk_id="c1", content="contingut MANIPULAT") is False
    # Sense procedència registrada → invàlid.
    assert reg.is_valid(chunk_id="desconegut", content="x") is False


def test_filter_descarta_enverinats_i_sense_procedencia():
    reg = ProvenanceRegistry()
    reg.register(chunk_id="c1", source_id="doc:a", content="A")
    reg.register(chunk_id="c2", source_id="doc:b", content="B")
    chunks = [
        {"id": "c1", "content": "A"},              # vàlid
        {"id": "c2", "content": "B-MANIPULAT"},    # hash alterat → descartat
        {"id": "c3", "content": "sense procedència"},  # no registrat → descartat
    ]
    kept, dropped = filter_valid_chunks(reg, chunks)
    assert [c["id"] for c in kept] == ["c1"]
    assert {c["id"] for c in dropped} == {"c2", "c3"}
