"""K2.3 — Taxonomia de risc."""

from __future__ import annotations

import pytest

from app.risk import RiskLevel, parse_risk


def test_ordre_i_etiquetes():
    assert RiskLevel.INFO < RiskLevel.READ < RiskLevel.WRITE_LOCAL < RiskLevel.WRITE_EXTERNAL < RiskLevel.IRREVERSIBLE
    assert [r.etiqueta for r in RiskLevel] == ["info", "read", "write-local", "write-external", "irreversible"]
    assert int(RiskLevel.IRREVERSIBLE) == 4


@pytest.mark.parametrize("entrada,esperat", [
    (0, RiskLevel.INFO), (4, RiskLevel.IRREVERSIBLE),
    ("read", RiskLevel.READ), ("WRITE_LOCAL", RiskLevel.WRITE_LOCAL),
    ("write-external", RiskLevel.WRITE_EXTERNAL), ("3", RiskLevel.WRITE_EXTERNAL),
    (RiskLevel.READ, RiskLevel.READ),
])
def test_parse_risk(entrada, esperat):
    assert parse_risk(entrada) == esperat


def test_parse_risk_invalid():
    with pytest.raises(ValueError):
        parse_risk("nuclear")
