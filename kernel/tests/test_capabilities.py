"""K2.2 — Capability tokens JWT de vida curta."""

from __future__ import annotations

import datetime as dt

import pytest

from app.capabilities import CapabilityIssuer
from app.errors import CapabilityError

# Valor de test de baixa entropia (no és cap secret real): >= 16 car. per a l'issuer.
SECRET = "kernel-test-capability-secret-not-real"


def _issuer(**kw):
    return CapabilityIssuer(SECRET, **kw)


def test_mint_i_verify_ok():
    iss = _issuer()
    tok = iss.mint(tool_id="fs.read", session_id="s1", tenant_id="tA", risk_level=1)
    claims = iss.verify(tok, expected_tool_id="fs.read", expected_session_id="s1")
    assert claims.tool_id == "fs.read" and claims.session_id == "s1"
    assert claims.tenant_id == "tA" and claims.risk_level == 1
    assert claims.jti and claims.exp > claims.iat


def test_ttl_acotat_60_300():
    assert _issuer(ttl_s=5).ttl_s == 60      # per sota del mínim → 60
    assert _issuer(ttl_s=9999).ttl_s == 300  # per sobre del màxim → 300
    assert _issuer(ttl_s=120).ttl_s == 120


def test_token_caducat_rebutjat():
    iss = _issuer()
    passat = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1000)
    tok = iss.mint(tool_id="fs.read", session_id="s1", tenant_id="tA", risk_level=1, _now=passat)
    with pytest.raises(CapabilityError):
        iss.verify(tok, expected_tool_id="fs.read", expected_session_id="s1")


def test_tool_id_incorrecte_rebutjat():
    iss = _issuer()
    tok = iss.mint(tool_id="fs.read", session_id="s1", tenant_id="tA", risk_level=1)
    with pytest.raises(CapabilityError):
        iss.verify(tok, expected_tool_id="fs.write", expected_session_id="s1")


def test_session_incorrecta_rebutjada():
    iss = _issuer()
    tok = iss.mint(tool_id="fs.read", session_id="s1", tenant_id="tA", risk_level=1)
    with pytest.raises(CapabilityError):
        iss.verify(tok, expected_tool_id="fs.read", expected_session_id="ALTRA")


def test_signatura_manipulada_rebutjada():
    iss = _issuer()
    tok = iss.mint(tool_id="fs.read", session_id="s1", tenant_id="tA", risk_level=1)
    fals = tok[:-3] + ("aaa" if not tok.endswith("aaa") else "bbb")
    with pytest.raises(CapabilityError):
        iss.verify(fals, expected_tool_id="fs.read", expected_session_id="s1")


def test_secret_massa_curt():
    with pytest.raises(CapabilityError):
        CapabilityIssuer("curt")
