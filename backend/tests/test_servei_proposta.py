"""Servei intern del nucli (suite → core): POST /api/servei/proposta.

Verifica la frontera open-core de delegació d'inferència:
- desactivat (503) si no hi ha CORE_SERVICE_TOKEN configurat;
- 401 si el token de servei falta o no coincideix;
- 200 amb token vàlid: retorna una proposta (LLM doblat), marcada `assistit_per_ia`;
- el context del cridador (system propi, criteris, evidència) arriba al prompt.
"""

from __future__ import annotations

import pytest

TOKEN = "test-service-token-abcdef0123456789"


@pytest.fixture(autouse=True)
def _neteja_settings():
    """Cada test parteix d'una config neta (lru_cache) i la deixa neta després."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _activa_token(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("CORE_SERVICE_TOKEN", TOKEN)
    get_settings.cache_clear()


def test_servei_desactivat_sense_token(client):
    """Sense CORE_SERVICE_TOKEN (per defecte) el servei retorna 503."""
    r = client.post("/api/servei/proposta", json={"instruccions": "Fes una rúbrica."})
    assert r.status_code == 503


def test_servei_token_incorrecte(client, monkeypatch):
    _activa_token(monkeypatch)
    # Sense capçalera de servei → 401.
    r = client.post("/api/servei/proposta", json={"instruccions": "Hola."})
    assert r.status_code == 401
    # Amb token erroni → 401.
    r = client.post(
        "/api/servei/proposta",
        json={"instruccions": "Hola."},
        headers={"X-Service-Token": "dolent"},
    )
    assert r.status_code == 401


def test_servei_proposta_ok(client, monkeypatch):
    _activa_token(monkeypatch)
    r = client.post(
        "/api/servei/proposta",
        json={"instruccions": "Proposa una rúbrica per a sumes."},
        headers={"X-Service-Token": TOKEN},
    )
    assert r.status_code == 200
    cos = r.json()
    assert isinstance(cos["proposta"], str) and cos["proposta"]
    assert cos["assistit_per_ia"] is True
    assert cos["model"]  # informa el model local emprat
    assert cos["proposta_json"] is None  # no s'ha demanat format_json


def test_servei_bearer_tambe_val(client, monkeypatch):
    """El token de servei també s'accepta via Authorization: Bearer."""
    _activa_token(monkeypatch)
    r = client.post(
        "/api/servei/proposta",
        json={"instruccions": "Hola."},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert r.status_code == 200


def test_servei_context_arriba_al_prompt(client, monkeypatch, fake_llm):
    """Els criteris i l'evidència aportats pel suite s'injecten al prompt de l'LLM."""
    _activa_token(monkeypatch)
    r = client.post(
        "/api/servei/proposta",
        json={
            "instruccions": "Valora aquesta evidència segons els criteris.",
            "agent_id": "avaluacions",
            "criteris": ["MAT.5.1 · matemàtiques · 5è: resol problemes de sumes."],
            "evidencia": "L'alumne suma 12+9=21 i ho explica pas a pas.",
            "format_json": False,
        },
        headers={"X-Service-Token": TOKEN},
    )
    assert r.status_code == 200
    msgs = fake_llm.ultim_prompt
    assert msgs is not None
    sistema = msgs[0]["content"]
    usuari = msgs[1]["content"]
    # La persona de l'agent 'avaluacions' fonamenta el system.
    assert "avalua" in sistema.lower()
    # Criteris i evidència viatgen al missatge d'usuari.
    assert "MAT.5.1" in usuari
    assert "12+9=21" in usuari


def test_servei_guardrail_humanisme(client, monkeypatch, fake_llm):
    """El guardrail d'humanisme digital (C/2026/2826) governa CADA proposta i la
    resposta porta l'avís de transparència (art. 50)."""
    _activa_token(monkeypatch)
    r = client.post(
        "/api/servei/proposta",
        json={"instruccions": "Proposa una rúbrica."},
        headers={"X-Service-Token": TOKEN},
    )
    assert r.status_code == 200
    cos = r.json()
    # Avís de transparència humà present a la resposta.
    assert "C/2026/2826" in cos["avis"] and cos["assistit_per_ia"] is True
    # El guardrail s'ha injectat al system prompt del model.
    sistema = fake_llm.ultim_prompt[0]["content"]
    assert "DONES SUPORT, NO SUBSTITUEIXES" in sistema
    assert "C/2026/2826" in sistema


def test_servei_agent_tool_calling_no_permes(client, monkeypatch, fake_llm):
    """Un agent de tool-calling (assistent_admin) no s'usa com a persona: cau al
    system genèric (no s'injecta el seu prompt agèntic)."""
    _activa_token(monkeypatch)
    r = client.post(
        "/api/servei/proposta",
        json={"instruccions": "Fes alguna cosa.", "agent_id": "assistent_admin"},
        headers={"X-Service-Token": TOKEN},
    )
    assert r.status_code == 200
    # El system NO és el de l'assistent agèntic: usa el genèric pedagògic.
    assert "pedag" in (fake_llm.ultim_prompt[0]["content"].lower())
