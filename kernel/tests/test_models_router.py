"""K5.1/K5.2 — router de models locals; rebuig d'endpoints externs (INV-3 parcial)."""

from __future__ import annotations

import pytest

from app.errors import AllowlistError, ExternalEndpointError
from app.models_router import (
    ModelRouter, assert_local_endpoint, external_calls, load_models_manifest,
)


def test_endpoint_local_acceptat():
    assert assert_local_endpoint("http://ollama:11434/v1") == "ollama"
    assert assert_local_endpoint("http://127.0.0.1:11434/v1") == "127.0.0.1"


def test_endpoint_openai_rebutjat_a_arrencada():
    with pytest.raises(ExternalEndpointError):
        ModelRouter(base_url="https://api.openai.com/v1", allowed_models={"qwen2.5:7b"})


def test_external_calls_zero():
    # Cap crida externa es realitza mai: la mètrica roman 0 (INV-3 parcial).
    assert external_calls() == 0


def test_model_allowlist():
    r = ModelRouter(base_url="http://ollama:11434/v1", allowed_models={"qwen2.5:7b"})
    assert r.ensure_model("qwen2.5:7b") == "qwen2.5:7b"
    with pytest.raises(AllowlistError):
        r.ensure_model("gpt-4o")


def test_manifest_hash():
    m = load_models_manifest("/app/allowlist/models.yaml")
    assert "qwen2.5:7b" in m["models"] and len(m["sha256"]) == 64
    # Hash esperat correcte → OK; hash dolent → rebuig (K5.2).
    assert load_models_manifest("/app/allowlist/models.yaml", expected_sha256=m["sha256"])["models"]
    with pytest.raises(AllowlistError):
        load_models_manifest("/app/allowlist/models.yaml", expected_sha256="0" * 64)
