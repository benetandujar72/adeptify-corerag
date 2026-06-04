"""K1.1/K1.2/K1.4 — orquestrador determinista plan→act→observe."""

from __future__ import annotations

from app.orchestrator import Orchestrator, Plan


def test_pla_buit_no_executa_cap_eina(tool_kernel, make_session):
    orq = Orchestrator(tool_kernel)
    res = orq.run(make_session(role="operator"), Plan())
    assert res.completed is True
    assert res.observations == []
    assert tool_kernel.executed_count == 0  # cap herramienta executada


def test_happy_path(tool_kernel, make_session):
    orq = Orchestrator(tool_kernel)
    plan = Plan.from_list([{"tool_id": "echo.info", "args": {"msg": "ep"}}])
    res = orq.run(make_session(role="operator"), plan)
    assert res.completed is True and res.executed_ok == 1
    assert res.observations[0].result.echo == "ep"


def test_loop_limit_3_atura_al_pas_4(tool_kernel, make_session):
    orq = Orchestrator(tool_kernel)
    plan = Plan.from_list([{"tool_id": "echo.info", "args": {"msg": str(i)}} for i in range(5)])
    s = make_session(role="operator", max_steps=3)
    res = orq.run(s, plan)
    assert res.completed is False and res.escalated is True
    assert res.executed_ok == 3  # s'executen 3 i s'atura al pas 4
    assert "STEP_LIMIT" in (res.escalation_reason or "")
    assert tool_kernel.executed_count == 3


def test_timeout_absolut_escala(tool_kernel, make_session):
    orq = Orchestrator(tool_kernel)
    s = make_session(role="operator", timeout_s=0.0)  # deadline ja vençut
    res = orq.run(s, Plan.from_list([{"tool_id": "echo.info", "args": {"msg": "x"}}]))
    assert res.completed is False and res.escalated is True
    assert "SESSION_TIMEOUT" in (res.escalation_reason or "")
    assert tool_kernel.executed_count == 0


def test_denegacio_politica_atura_el_pla(tool_kernel, make_session):
    orq = Orchestrator(tool_kernel)
    s = make_session(role="viewer")
    res = orq.run(s, Plan.from_list([{"tool_id": "kv.put_local", "args": {"key": "k", "value": "v"}}]))
    assert res.completed is False and res.escalated is False
    assert res.observations[0].ok is False
    assert "PolicyDenied" in (res.observations[0].error or "")
