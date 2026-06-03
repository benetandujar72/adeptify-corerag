"""Tests de RBAC: accés a agents per rol i filtratge a /api/agents."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.agents.registry import agents_per_rol
from app.core.roles import Rol
from app.orchestrator import rbac


def test_agents_per_rol_alumne():
    ids = {a.id for a in agents_per_rol(Rol.ALUMNE)}
    assert ids == {"tutor_mates"}  # l'alumne només té el tutor


def test_agents_per_rol_familia():
    ids = {a.id for a in agents_per_rol(Rol.FAMILIA)}
    assert ids == {"secretaria", "families"}


def test_agents_per_rol_docent_inclou_copilot_didactic():
    ids = {a.id for a in agents_per_rol(Rol.DOCENT)}
    assert "copilot_didactic" in ids
    assert "copilot_exercicis" in ids
    assert "copilot_adaptacions" in ids
    assert "assistent_admin" not in ids


def test_agents_per_rol_direccio():
    ids = {a.id for a in agents_per_rol(Rol.DIRECCIO)}
    # Direcció té accés als agents de consulta + als agèntics (Fase 9).
    assert ids == {
        "secretaria", "documental", "avaluacions", "copilot_didactic",
        "copilot_context", "copilot_contingut", "copilot_format",
        "copilot_exercicis", "copilot_rubriques", "copilot_adaptacions",
        "copilot_seguiment", "copilot_butlleti", "copilot_qualitat",
        "assistent_admin", "seguiment_correu",
    }


def test_agents_per_rol_superadmin_tots():
    from app.agents.registry import AGENTS

    ids = {a.id for a in agents_per_rol(Rol.SUPERADMIN)}
    assert ids == set(AGENTS.keys())  # god mode: tots els agents


def test_comprova_acces_superadmin_qualsevol_agent():
    # El superadmin pot accedir a qualsevol agent (inclòs un que no el llista).
    assert rbac.comprova_acces_agent("tutor_mates", Rol.SUPERADMIN).id == "tutor_mates"
    assert rbac.comprova_acces_agent("seguiment_correu", Rol.SUPERADMIN).id == "seguiment_correu"


def test_comprova_acces_ok():
    agent = rbac.comprova_acces_agent("tutor_mates", Rol.DOCENT)
    assert agent.id == "tutor_mates"


def test_comprova_acces_copilot_docent_ok_i_familia_prohibit():
    assert rbac.comprova_acces_agent("copilot_didactic", Rol.DOCENT).id == "copilot_didactic"
    assert rbac.comprova_acces_agent("copilot_qualitat", Rol.DOCENT).id == "copilot_qualitat"
    with pytest.raises(HTTPException) as exc:
        rbac.comprova_acces_agent("copilot_didactic", Rol.FAMILIA)
    assert exc.value.status_code == 403


def test_comprova_acces_prohibit():
    with pytest.raises(HTTPException) as exc:
        rbac.comprova_acces_agent("tutor_mates", Rol.FAMILIA)
    assert exc.value.status_code == 403


def test_comprova_acces_agent_inexistent():
    with pytest.raises(HTTPException) as exc:
        rbac.comprova_acces_agent("inexistent", Rol.DOCENT)
    assert exc.value.status_code == 404


def test_endpoint_agents_filtra_per_rol(client, token_alumne):
    resp = client.get(
        "/api/agents", headers={"Authorization": f"Bearer {token_alumne}"}
    )
    assert resp.status_code == 200
    ids = {a["id"] for a in resp.json()["agents"]}
    assert ids == {"tutor_mates"}


def test_chat_prohibit_retorna_403(client, token_familia, document_indexat):
    # Una família intenta parlar amb el tutor de mates (no permès).
    resp = client.post(
        "/api/chat",
        headers={"Authorization": f"Bearer {token_familia}"},
        json={"agent_id": "tutor_mates", "message": "Hola", "stream": False},
    )
    # L'orquestrador reencamina a un agent accessible o bloqueja; en cap cas
    # la família pot acabar parlant amb tutor_mates.
    if resp.status_code == 200:
        assert resp.json()["agent_utilitzat"] != "tutor_mates"
    else:
        assert resp.status_code == 403
        assert resp.json()["error"]["codi"] == "FORBIDDEN"
