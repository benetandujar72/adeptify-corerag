"""Red-team adversarial de F5 (capa conversacional): forats tancats a la revisió.

Cada test correspon a un vector provat contra intent (F5a) / memòria (F5b) / triggers
(F5c) / bucle (F5d). Mantenir-los verds = els forats segueixen tancats."""

from __future__ import annotations

import pytest

from app.allowlist import load_signed_allowlist
from app.conversa import BuclePropose, EstatProposta
from app.errors import TascaError, TriggerError
from app.intent import IntentResolver
from app.orchestrator import Orchestrator
from app.playbooks import load_signed_playbooks
from app.task_memory import EstatTasca, MemoriaTasques
from app.triggers import SignedTrigger, TriggerCondicio, avalua, load_signed_triggers

AL = "/app/allowlist"

_PLAYBOOKS_YAML = """
playbooks:
  - id: consulta_doc
    descripcio: Consulta un document sintetic
    alias:
      - consultar document
    risc_max: read
    passos:
      - tool_id: fs.read_synthetic
        args:
          doc_id: "guia"
  - id: desa_nota
    descripcio: Desa una nota local
    alias:
      - guardar nota
      - desa apunt
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
"""


@pytest.fixture()
def allowlist():
    return load_signed_allowlist(
        data_path=f"{AL}/tools.yaml", sig_path=f"{AL}/tools.yaml.sig", pubkey_path=f"{AL}/pubkey.asc",
    )


@pytest.fixture()
def catalog(tmp_path, allowlist):
    f = tmp_path / "pb.yaml"
    f.write_text(_PLAYBOOKS_YAML, encoding="utf-8")
    return load_signed_playbooks(data_path=str(f), sig_path="x", pubkey_path="x",
                                 allowlist=allowlist, verify=False)


# ── F5a · PII OFUSCADA amb Unicode de doble amplada (evadiria el regex sobre cru) ──
@pytest.mark.parametrize("text", [
    "guardar nota a pare＠exemple.cat",          # '＠' U+FF20 → NFKD '@'
    "desa apunt tel ６００１２３４５６",            # dígits de doble amplada → 600123456
])
def test_pii_ofuscada_fullwidth_es_rebutja(catalog, text):
    r = IntentResolver(catalog).resol(text)
    assert r.refusat_pii is True and r.match is None


# ── F5a · ENUM tancat: cap entrada fa sortir un id fora del catàleg ──
def test_enum_tancat_robust(catalog):
    res = IntentResolver(catalog)
    for txt in ["../../etc/passwd", "desa_nota; rm -rf", "{param:x}", "exec(open())",
                "consultar document", "DROP TABLE", ""]:
        r = res.resol(txt)
        assert r.match is None or r.match in catalog.ids


# ── F5b · param NIAT amagaria PII a l'inspector escalar ──
def test_param_niat_es_rebutja(make_session):
    mem = MemoriaTasques()
    with pytest.raises(TascaError):
        mem.registra_proposta(session=make_session(), playbook_id="p",
                              params={"x": {"dni": "12345678Z"}})
    with pytest.raises(TascaError):
        mem.registra_proposta(session=make_session(), playbook_id="p",
                              params={"x": ["pare@exemple.cat"]})


# ── F5c · valor no finit en trigger signat (nan: «!=» dispararia sempre) ──
def test_trigger_valor_no_finit_es_rebutja(tmp_path, catalog):
    for v in ("nan", "inf", "-inf"):
        f = tmp_path / f"trig_{v}.yaml"
        f.write_text(f"""
triggers:
  - id: t
    playbook: desa_nota
    condicio:
      camp: x
      op: "!="
      valor: "{v}"
""", encoding="utf-8")
        with pytest.raises(TriggerError):
            load_signed_triggers(data_path=str(f), sig_path="x", pubkey_path="x",
                                 playbooks=catalog, verify=False)


def test_trigger_snapshot_no_finit_no_dispara():
    t = SignedTrigger("t", "p", TriggerCondicio("x", "!=", 0.0))
    assert avalua(t, {"x": float("nan")}) is False  # fail-closed, no dispar fantasma
    assert avalua(t, {"x": float("inf")}) is False


# ── F5d · re-confirmar una tasca ja EXECUTADA es rebutja ──
def test_reconfirma_executada_es_rebutja(catalog, allowlist, approval_gate, make_session,
                                         gated_tool_kernel):
    mem = MemoriaTasques()
    bucle = BuclePropose(catalog=catalog, allowlist=allowlist, gate=approval_gate,
                         resolver=IntentResolver(catalog), memoria=mem)
    orch = Orchestrator(gated_tool_kernel)
    sess = make_session(role="operator")
    res = bucle.proposa(session=sess, text_nl="consultar document")  # READ → cap aprovació
    conf = bucle.confirma(session=sess, tasca_id=res.tasca.tasca_id, orchestrator=orch)
    assert conf.executat and conf.tasca.estat is EstatTasca.EXECUTADA
    with pytest.raises(TascaError):  # ja terminal → res a confirmar
        bucle.confirma(session=sess, tasca_id=res.tasca.tasca_id, orchestrator=orch)


# ── F5d · token d'aprovació FALSIFICAT no executa res ──
def test_token_falsificat_no_executa(catalog, allowlist, approval_gate, make_session,
                                     gated_tool_kernel):
    mem = MemoriaTasques()
    bucle = BuclePropose(catalog=catalog, allowlist=allowlist, gate=approval_gate,
                         resolver=IntentResolver(catalog), memoria=mem)
    orch = Orchestrator(gated_tool_kernel)
    sess = make_session(role="operator")
    res = bucle.proposa(session=sess, text_nl="guardar nota",
                        params={"clau": "k", "valor": "v"})
    req = res.requests[0]
    conf = bucle.confirma(session=sess, tasca_id=res.tasca.tasca_id, orchestrator=orch,
                          approvals={req.request_id: "ey.fals.token"})
    assert conf.executat is False
    assert conf.tasca.estat is EstatTasca.PROPOSADA       # reintentable
    assert gated_tool_kernel.executed_count == 0
