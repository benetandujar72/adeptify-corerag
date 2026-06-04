"""K3.3 — pin/firma SHA-256 de servidors MCP locals."""

from __future__ import annotations

import pytest

from app.errors import McpPinError
from app.mcp_pin import McpPinRegistry, descriptor_hash


def test_verify_ok():
    desc = b'{"name":"rag-local","version":"1"}'
    reg = McpPinRegistry({"rag-local": descriptor_hash(desc)})
    pin = reg.verify("rag-local", desc)
    assert pin.name == "rag-local"


def test_servidor_sense_pin_rebutjat():
    reg = McpPinRegistry({"rag-local": descriptor_hash(b"x")})
    with pytest.raises(McpPinError):
        reg.verify("desconegut", b"x")  # sense pin conegut → rebuig


def test_descriptor_modificat_rebutjat():
    desc = b'{"name":"rag-local","version":"1"}'
    reg = McpPinRegistry({"rag-local": descriptor_hash(desc)})
    with pytest.raises(McpPinError):
        reg.verify("rag-local", b'{"name":"rag-local","version":"2-MODIFICAT"}')
