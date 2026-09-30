"""AGPL-3.0 §13: el codi font s'ofereix a qui fa servir el nucli per la xarxa (`GET /api/codi-font`)."""

from __future__ import annotations

from app.core.config import get_settings


def test_el_codi_font_s_ofereix_sense_autenticacio(client):
    r = client.get("/api/codi-font")
    assert r.status_code == 200
    cos = r.json()
    assert cos["llicencia"] == "AGPL-3.0-or-later"
    assert cos["repositori"].startswith("https://github.com/") and cos["commit"] is None
    assert cos["text_llicencia"].endswith("/LICENSE")


def test_amb_el_commit_desplegat_apunta_a_aquell_codi(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "codi_font_url", "https://git.example.org/fork/")
    monkeypatch.setattr(s, "codi_font_commit", "abc1234")
    cos = client.get("/api/codi-font").json()
    assert cos["repositori"] == "https://git.example.org/fork/tree/abc1234"
    assert cos["text_llicencia"] == "https://git.example.org/fork/blob/abc1234/LICENSE"
