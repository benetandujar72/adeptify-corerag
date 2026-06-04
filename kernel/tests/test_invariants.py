"""Banc d'invariants (Prompt V parcial) — INV-1..INV-5.

Cada test demostra una invariant inviolable amb evidència executable.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.errors import (
    AllowlistError, ArbitraryCodeError, ExternalEndpointError, PolicyDenied,
)
from app.models_router import ModelRouter, external_calls
from app.risk import RiskLevel
from app.tools import Tool
from app.vault import Vault, assert_no_secrets

APP_DIR = pathlib.Path("/app/app")
# Detectem CRIDES reals (no mencions en patrons/strings de detecció). El negative
# lookbehind evita falsos positius com el patró `\beval\s*\(` dins de guardrails.py.
_DANGER = [
    (re.compile(r"\bimport\s+subprocess\b"), "import subprocess"),
    (re.compile(r"\bsubprocess\s*\.\s*\w"), "subprocess.<call>"),
    (re.compile(r"\bos\.system\s*\("), "os.system("),
    (re.compile(r"\bos\.popen\s*\("), "os.popen("),
    (re.compile(r"(?<![\\\w.])eval\s*\("), "eval("),
    (re.compile(r"(?<![\\\w.])exec\s*\("), "exec("),
    (re.compile(r"(?<![\\\w.])__import__\s*\("), "__import__("),
    (re.compile(r"\bpickle\.loads?\s*\("), "pickle.load("),
]


def test_inv1_cap_execucio_de_codi_arbitrari():
    """INV-1: el codi del kernel no fa cap CRIDA d'execució arbitrària, i una
    eina ha de ser un callable pre-registrat (no codi del xat/doc/resultat)."""
    for py in sorted(APP_DIR.glob("*.py")):
        src = py.read_text(encoding="utf-8")
        for rx, label in _DANGER:
            assert not rx.search(src), f"{py.name} fa una crida prohibida: {label} (INV-1)"


def test_inv1_eina_no_callable_rebutjada(tool_kernel):
    from pydantic import BaseModel

    class _A(BaseModel):
        pass

    bad = Tool("echo.info", RiskLevel.INFO, _A, _A, fn="rm -rf /")  # type: ignore[arg-type]
    with pytest.raises(ArbitraryCodeError):
        tool_kernel.register(bad)


def test_inv2_rbac_al_kernel(tool_kernel, make_session):
    """INV-2: el RBAC el decideix el kernel d'eines, no el model."""
    with pytest.raises(PolicyDenied):
        tool_kernel.invoke(session=make_session(role="viewer"), tool_id="kv.put_local",
                           args={"key": "k", "value": "v"})


def test_inv3_zero_egress_rebutja_extern():
    """INV-3 (parcial, capa app): cap endpoint fora de la LAN; external_calls=0."""
    with pytest.raises(ExternalEndpointError):
        ModelRouter(base_url="https://api.openai.com/v1", allowed_models={"qwen2.5:7b"})
    assert external_calls() == 0


def test_inv4_sense_eines_dinamiques(tool_kernel):
    """INV-4: no es pot registrar cap eina fora de l'allowlist signada."""
    from pydantic import BaseModel

    class _A(BaseModel):
        pass

    with pytest.raises(AllowlistError):
        tool_kernel.register(Tool("agent.spawn", RiskLevel.IRREVERSIBLE, _A, _A, lambda a, c, x: {}))


def test_inv5_cap_secret_al_context_del_model():
    """INV-5: cap valor del vault apareix al context destinat al model."""
    v = Vault({"KERNEL_CAPABILITY_SECRET": "super-secret-xyz-123"})
    context_net = {"system": "Ets un assistent.", "user": "Quins documents hi ha?", "fonts": ["doc1"]}
    assert_no_secrets(context_net, v)  # no llança
    context_brut = {"system": "clau=super-secret-xyz-123"}
    with pytest.raises(AssertionError):
        assert_no_secrets(context_brut, v)
