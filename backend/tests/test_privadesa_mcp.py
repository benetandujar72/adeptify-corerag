"""Tests de privadesa (zero crides a tercers) i de la capa MCP."""

from __future__ import annotations

import pytest

from app.core import telemetria
from app.mcp.server import get_mcp_server


def test_domini_prohibit_detectat():
    assert telemetria.es_domini_prohibit("https://api.openai.com/v1") is True
    assert telemetria.es_domini_prohibit("https://api.anthropic.com") is True
    assert telemetria.es_domini_prohibit("http://ollama:11434/v1") is False
    assert telemetria.es_domini_prohibit("http://vllm:8000/v1") is False


def test_client_llm_bloqueja_domini_prohibit(monkeypatch):
    # Si OPENAI_BASE_URL apunta a un proveïdor comercial, el client ha de fallar.
    from app.core.config import Settings
    from app.rag.llm import OpenAICompatibleClient

    settings = Settings(openai_base_url="https://api.openai.com/v1")
    with pytest.raises(RuntimeError):
        OpenAICompatibleClient(settings)
    assert telemetria.crides_externes() >= 1


def test_mcp_llista_i_invoca_tools(db, document_indexat):
    servidor = get_mcp_server(db)
    noms = servidor.noms()
    assert {"drive", "materials", "base_nofc_pec", "calendari"} <= set(noms)

    # Descriptors estil MCP tools/list.
    descriptors = servidor.llista_tools(["base_nofc_pec"])
    assert descriptors[0]["name"] == "base_nofc_pec"
    assert "inputSchema" in descriptors[0]

    # Invocació d'una tool que cerca al document indexat.
    res = servidor.invoca("base_nofc_pec", consulta="esquí")
    assert res.ok is True
    assert any("SOR-001" in str(item) for item in res.contingut) or res.contingut == []


def test_mcp_tool_desconeguda(db):
    servidor = get_mcp_server(db)
    res = servidor.invoca("inexistent", consulta="x")
    assert res.ok is False
    assert res.error
