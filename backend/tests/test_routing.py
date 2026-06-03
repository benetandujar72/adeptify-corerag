"""Tests del routing de l'orquestrador (classificació d'intenció i llengua)."""

from __future__ import annotations

from app.core.roles import Rol
from app.orchestrator.router import classifica, detecta_llengua


def test_respecta_agent_suggerit_si_es_accessible():
    decisio = classifica(
        "Tinc un dubte general", agent_suggerit="tutor_mates", rol=Rol.DOCENT
    )
    assert decisio.agent_id == "tutor_mates"
    assert decisio.reencaminat is False


def test_reencamina_a_secretaria_per_normativa():
    # Un alumne pregunta de mates → tutor; però amb paraules de normativa fortes
    # i un agent accessible millor, l'orquestrador pot reencaminar.
    decisio = classifica(
        "Quins són els festius i la normativa NOFC del calendari?",
        agent_suggerit="tutor_mates",
        rol=Rol.DOCENT,
    )
    assert decisio.agent_id == "secretaria"
    assert decisio.reencaminat is True


def test_routing_respecta_rbac_quan_suggerit_no_es_accessible():
    # Una família NO pot accedir a tutor_mates; el routing tria entre els seus.
    decisio = classifica(
        "Quin dia surt el curs a l'esquí?",
        agent_suggerit="tutor_mates",
        rol=Rol.FAMILIA,
    )
    assert decisio.agent_id in {"families", "secretaria"}


def test_detecta_llengua_castella():
    assert detecta_llengua("¿Cuándo es la salida y el horario del comedor?") == "es"


def test_detecta_llengua_catala():
    assert detecta_llengua("Quin dia és la sortida i l'horari del menjador?") == "ca"


def test_etiqueta_intencio_per_agent():
    decisio = classifica(
        "Ajuda'm amb un problema de fraccions", "tutor_mates", Rol.ALUMNE
    )
    assert decisio.agent_id == "tutor_mates"
    assert decisio.intencio == "consulta_matematiques"
