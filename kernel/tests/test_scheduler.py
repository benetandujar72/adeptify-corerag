"""K11 (F4) — Scheduler PROPOSE-ONLY: due determinista (sense dep) + proposta sense execució."""

from __future__ import annotations

import datetime as dt

import pytest

from app.allowlist import load_signed_allowlist
from app.errors import SchedulerError
from app.orchestrator import Plan
from app.playbooks import load_signed_playbooks
from app.scheduler import (
    RUNNER_ACTIU,
    is_due,
    load_signed_schedule,
    materialitza_proposta,
    tasques_due,
)

AL = "/app/allowlist"
UTC = dt.timezone.utc


def _ts(y, mo, d, h, mi) -> float:
    return dt.datetime(y, mo, d, h, mi, tzinfo=UTC).timestamp()


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


def _schedule_yaml(tmp_path, contingut: str) -> str:
    f = tmp_path / "schedule.yaml"
    f.write_text(contingut, encoding="utf-8")
    return str(f)


# ── is_due (determinista, sense dep) ─────────────────────────────────────────
def test_is_due_interval():
    spec = {"tipus": "interval", "segons": 3600}
    ara = _ts(2026, 6, 5, 12, 0)
    assert is_due(spec, last_fire=None, now=ara) is True            # mai tret → toca
    assert is_due(spec, last_fire=ara - 100, now=ara) is False      # fa 100s → no
    assert is_due(spec, last_fire=ara - 4000, now=ara) is True      # fa >1h → sí


def test_is_due_diari():
    spec = {"tipus": "diari", "hora": 7, "minut": 0}
    ara = _ts(2026, 6, 5, 9, 0)                       # 09:00 UTC, objectiu avui 07:00
    assert is_due(spec, last_fire=None, now=ara) is True
    assert is_due(spec, last_fire=_ts(2026, 6, 5, 8, 0), now=ara) is False   # ja tret avui
    assert is_due(spec, last_fire=_ts(2026, 6, 4, 7, 30), now=ara) is True   # ahir → toca
    # Abans de l'hora (06:00) i ja tret ahir → no toca encara.
    matí = _ts(2026, 6, 5, 6, 0)
    assert is_due(spec, last_fire=_ts(2026, 6, 4, 7, 30), now=matí) is False


def test_is_due_tipus_desconegut():
    with pytest.raises(SchedulerError):
        is_due({"tipus": "lunar"}, last_fire=None, now=_ts(2026, 6, 5, 9, 0))


def test_runner_off_per_defecte():
    assert RUNNER_ACTIU is False  # cap execució autònoma (gate G-G, fail-closed)


# ── Càrrega + validació encreuada ────────────────────────────────────────────
def test_carrega_schedule_ok(tmp_path, playbooks):
    path = _schedule_yaml(tmp_path, """
tasques:
  - id: nota_diaria
    playbook: desa_nota
    params:
      clau: salutacio
      valor: hola
    schedule:
      tipus: diari
      hora: "7"
      minut: "0"
""")
    cat = load_signed_schedule(data_path=path, sig_path="x", pubkey_path="x",
                               playbooks=playbooks, verify=False)
    assert "nota_diaria" in cat and cat.get("nota_diaria").playbook_id == "desa_nota"


def test_schedule_playbook_inexistent_rebutjat(tmp_path, playbooks):
    path = _schedule_yaml(tmp_path, """
tasques:
  - id: t
    playbook: no_existeix
    schedule:
      tipus: interval
      segons: "60"
""")
    with pytest.raises(SchedulerError):
        load_signed_schedule(data_path=path, sig_path="x", pubkey_path="x",
                             playbooks=playbooks, verify=False)


def test_schedule_spec_invalid_rebutjat(tmp_path, playbooks):
    path = _schedule_yaml(tmp_path, """
tasques:
  - id: t
    playbook: desa_nota
    schedule:
      tipus: lunar
""")
    with pytest.raises(SchedulerError):
        load_signed_schedule(data_path=path, sig_path="x", pubkey_path="x",
                             playbooks=playbooks, verify=False)


def test_tasques_due(tmp_path, playbooks):
    path = _schedule_yaml(tmp_path, """
tasques:
  - id: cada_minut
    playbook: desa_nota
    params:
      clau: c
      valor: v
    schedule:
      tipus: interval
      segons: "60"
""")
    cat = load_signed_schedule(data_path=path, sig_path="x", pubkey_path="x",
                               playbooks=playbooks, verify=False)
    ara = _ts(2026, 6, 5, 12, 0)
    assert [t.id for t in tasques_due(cat, now=ara)] == ["cada_minut"]
    # Acabada de tret → ja no toca.
    assert tasques_due(cat, now=ara, ultim_tret={"cada_minut": ara - 5}) == []


# ── Red-team F4: validació de spec a la càrrega (fail-closed) ────────────────
def test_schedule_spec_camps_invalids_rebutjat(tmp_path, playbooks):
    # interval sense segons.
    p1 = _schedule_yaml(tmp_path, """
tasques:
  - id: t
    playbook: desa_nota
    schedule:
      tipus: interval
""")
    with pytest.raises(SchedulerError):
        load_signed_schedule(data_path=p1, sig_path="x", pubkey_path="x",
                             playbooks=playbooks, verify=False)
    # diari amb hora fora de rang.
    p2 = _schedule_yaml(tmp_path, """
tasques:
  - id: t
    playbook: desa_nota
    schedule:
      tipus: diari
      hora: "99"
      minut: "0"
""")
    with pytest.raises(SchedulerError):
        load_signed_schedule(data_path=p2, sig_path="x", pubkey_path="x",
                             playbooks=playbooks, verify=False)


# ── PROPOSE-ONLY: materialitza proposta SENSE executar ───────────────────────
def test_materialitza_proposta_no_executa(tmp_path, playbooks, allowlist, approval_gate, make_session):
    cat = load_signed_schedule(data_path=_schedule_yaml(tmp_path, """
tasques:
  - id: nota
    playbook: desa_nota
    params:
      clau: salutacio
      valor: hola
    schedule:
      tipus: interval
      segons: "60"
"""), sig_path="x", pubkey_path="x", playbooks=playbooks, verify=False)
    task = cat.get("nota")
    sess = make_session(role="operator")
    prop = materialitza_proposta(task, playbooks=playbooks, allowlist=allowlist,
                                 gate=approval_gate, session=sess)
    # S'ha materialitzat el Plan i s'ha ENCUAT una proposta d'aprovació (write-local → 1).
    assert isinstance(prop.plan, Plan) and len(prop.plan.steps) == 1
    assert prop.plan.steps[0].tool_id == "kv.put_local"
    assert prop.plan.steps[0].args == {"key": "salutacio", "value": "hola"}
    assert len(prop.requests) == 1 and prop.requests[0].aprovacions_requerides == 1
    # PENDING_APPROVAL al gate; NO s'ha executat res (cap token, cap invoke).
    assert prop.requests[0].request_id in approval_gate._pending
    assert prop.requests[0].resum  # resum NL determinista (K6.2)
