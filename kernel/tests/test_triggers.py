"""K15·F5c — Triggers declaratius signats: avaluació PURA + propose-only (sense runner)."""

from __future__ import annotations

import pytest

from app.allowlist import load_signed_allowlist
from app.errors import TriggerError
from app.orchestrator import Plan
from app.playbooks import load_signed_playbooks
from app.triggers import (
    RUNNER_ACTIU,
    SignedTrigger,
    TriggerCondicio,
    avalua,
    load_signed_triggers,
    materialitza_proposta_trigger,
    triggers_actius,
)

AL = "/app/allowlist"


@pytest.fixture()
def allowlist():
    return load_signed_allowlist(
        data_path=f"{AL}/tools.yaml", sig_path=f"{AL}/tools.yaml.sig", pubkey_path=f"{AL}/pubkey.asc",
    )


@pytest.fixture()
def playbooks(tmp_path, allowlist):
    f = tmp_path / "playbooks.yaml"
    f.write_text("""
playbooks:
  - id: desa_nota
    descripcio: Desa una nota local
    risc_max: write-local
    params:
      - nom: clau
        tipus: str
      - nom: valor
        tipus: str
    passos:
      - tool_id: kv.put_local
        args:
          key: "{param:clau}"
          value: "{param:valor}"
""", encoding="utf-8")
    return load_signed_playbooks(data_path=str(f), sig_path="x", pubkey_path="x",
                                 allowlist=allowlist, verify=False)


def _triggers_yaml(tmp_path, contingut: str) -> str:
    f = tmp_path / "triggers.yaml"
    f.write_text(contingut, encoding="utf-8")
    return str(f)


# ── Sense runner autònom (gate G-G/G-A) ──────────────────────────────────────
def test_runner_off():
    assert RUNNER_ACTIU is False


# ── Avaluació PURA de la condició ────────────────────────────────────────────
def test_avalua_condicio():
    t = SignedTrigger("t", "p", TriggerCondicio("pendents", ">=", 10.0))
    assert avalua(t, {"pendents": 12}) is True
    assert avalua(t, {"pendents": 3}) is False
    # Camp absent → fail-closed (no es dispara).
    assert avalua(t, {}) is False
    assert avalua(t, {"altre": 99}) is False


def test_avalua_booleans():
    t = SignedTrigger("t", "p", TriggerCondicio("actiu", "==", 1.0))
    assert avalua(t, {"actiu": True}) is True
    assert avalua(t, {"actiu": False}) is False


def test_avalua_rebutja_no_numeric():
    t = SignedTrigger("t", "p", TriggerCondicio("nom", "==", 1.0))
    with pytest.raises(TriggerError):  # el CORE no compara strings lliures (possible PII)
        avalua(t, {"nom": "alumne X amb DNI"})


# ── Càrrega + validació encreuada ────────────────────────────────────────────
def test_carrega_ok(tmp_path, playbooks):
    path = _triggers_yaml(tmp_path, """
triggers:
  - id: massa_pendents
    playbook: desa_nota
    params:
      clau: avis
      valor: revisa
    condicio:
      camp: pendents
      op: ">="
      valor: "10"
""")
    cat = load_signed_triggers(data_path=path, sig_path="x", pubkey_path="x",
                               playbooks=playbooks, verify=False)
    assert "massa_pendents" in cat
    assert cat.require("massa_pendents").condicio.op == ">="
    assert triggers_actius(cat, {"pendents": 11})[0].id == "massa_pendents"
    assert triggers_actius(cat, {"pendents": 1}) == []


def test_playbook_inexistent_rebutjat(tmp_path, playbooks):
    path = _triggers_yaml(tmp_path, """
triggers:
  - id: t
    playbook: no_existeix
    condicio:
      camp: x
      op: ">"
      valor: "1"
""")
    with pytest.raises(TriggerError):
        load_signed_triggers(data_path=path, sig_path="x", pubkey_path="x",
                             playbooks=playbooks, verify=False)


def test_operador_no_permes_rebutjat(tmp_path, playbooks):
    path = _triggers_yaml(tmp_path, """
triggers:
  - id: t
    playbook: desa_nota
    condicio:
      camp: x
      op: "=~"
      valor: "1"
""")
    with pytest.raises(TriggerError):
        load_signed_triggers(data_path=path, sig_path="x", pubkey_path="x",
                             playbooks=playbooks, verify=False)


def test_valor_no_numeric_rebutjat(tmp_path, playbooks):
    path = _triggers_yaml(tmp_path, """
triggers:
  - id: t
    playbook: desa_nota
    condicio:
      camp: x
      op: ">"
      valor: "molt"
""")
    with pytest.raises(TriggerError):
        load_signed_triggers(data_path=path, sig_path="x", pubkey_path="x",
                             playbooks=playbooks, verify=False)


# ── PROPOSE-ONLY: materialitza proposta SENSE executar ───────────────────────
def test_materialitza_proposta_no_executa(tmp_path, playbooks, allowlist, approval_gate, make_session):
    cat = load_signed_triggers(data_path=_triggers_yaml(tmp_path, """
triggers:
  - id: massa_pendents
    playbook: desa_nota
    params:
      clau: avis
      valor: revisa
    condicio:
      camp: pendents
      op: ">="
      valor: "10"
"""), sig_path="x", pubkey_path="x", playbooks=playbooks, verify=False)
    trig = cat.require("massa_pendents")
    sess = make_session(role="operator")
    prop = materialitza_proposta_trigger(trig, playbooks=playbooks, allowlist=allowlist,
                                         gate=approval_gate, session=sess)
    assert isinstance(prop.plan, Plan) and len(prop.plan.steps) == 1
    assert prop.plan.steps[0].tool_id == "kv.put_local"
    assert prop.plan.steps[0].args == {"key": "avis", "value": "revisa"}
    assert len(prop.requests) == 1 and prop.requests[0].aprovacions_requerides == 1
    # PENDING_APPROVAL al gate; cap execució (cap invoke).
    assert prop.requests[0].request_id in approval_gate._pending
