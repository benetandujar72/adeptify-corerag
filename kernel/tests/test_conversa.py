"""K16·F5d — Bucle propose→confirm: sense execució a propose, execució SEMPRE via Orchestrator."""

from __future__ import annotations

import pytest

from app.allowlist import load_signed_allowlist
from app.conversa import BuclePropose, EstatProposta
from app.intent import IntentResolver
from app.orchestrator import Orchestrator
from app.playbooks import load_signed_playbooks
from app.task_memory import EstatTasca, MemoriaTasques

AL = "/app/allowlist"

# `consulta_doc` (READ → sense aprovació) i `desa_nota` (WRITE_LOCAL → 1 aprovació).
# Tot block-style: strictyaml NO admet flow style ([], {}).
_PLAYBOOKS_YAML = """
playbooks:
  - id: consulta_doc
    descripcio: Consulta un document sintetic del centre
    alias:
      - consultar document
      - llegir doc
    risc_max: read
    passos:
      - tool_id: fs.read_synthetic
        args:
          doc_id: "guia"
  - id: desa_nota
    descripcio: Desa una nota local al quadern
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
    f = tmp_path / "playbooks.yaml"
    f.write_text(_PLAYBOOKS_YAML, encoding="utf-8")
    return load_signed_playbooks(data_path=str(f), sig_path="x", pubkey_path="x",
                                 allowlist=allowlist, verify=False)


@pytest.fixture()
def memoria():
    return MemoriaTasques()


@pytest.fixture()
def bucle(catalog, allowlist, approval_gate, memoria):
    # El gate del bucle és el MATEIX que el del gated_tool_kernel (fixture approval_gate)
    # → els tokens aprovats casen a l'invoke.
    return BuclePropose(catalog=catalog, allowlist=allowlist, gate=approval_gate,
                        resolver=IntentResolver(catalog), memoria=memoria)


@pytest.fixture()
def orch(gated_tool_kernel):
    return Orchestrator(gated_tool_kernel)


# ── PROPOSE no executa res ───────────────────────────────────────────────────
def test_proposa_no_executa(bucle, make_session, gated_tool_kernel):
    sess = make_session(role="operator")
    res = bucle.proposa(session=sess, text_nl="guardar nota",
                        params={"clau": "x", "valor": "y"})
    assert res.estat is EstatProposta.PROPOSAT
    assert res.tasca.estat is EstatTasca.PROPOSADA
    assert len(res.requests) == 1 and res.requests[0].aprovacions_requerides == 1
    assert gated_tool_kernel.executed_count == 0  # res s'ha executat


def test_proposa_cap_coincidencia(bucle, make_session):
    res = bucle.proposa(session=make_session(), text_nl="quin temps fa a la lluna")
    assert res.estat is EstatProposta.CAP
    assert res.tasca is None and res.requests == ()


def test_proposa_refusa_pii(bucle, make_session):
    res = bucle.proposa(session=make_session(), text_nl="guardar nota DNI 12345678Z")
    assert res.estat is EstatProposta.REBUTJAT_PII
    assert res.tasca is None


# ── CONFIRM camí READ (sense aprovació) → executa via Orchestrator ───────────
def test_confirma_read_executa(bucle, make_session, orch, gated_tool_kernel):
    sess = make_session(role="operator")
    res = bucle.proposa(session=sess, text_nl="consultar document")
    assert res.estat is EstatProposta.PROPOSAT and res.requests == ()  # READ → cap aprovació
    conf = bucle.confirma(session=sess, tasca_id=res.tasca.tasca_id, orchestrator=orch)
    assert conf.executat is True
    assert conf.tasca.estat is EstatTasca.EXECUTADA
    assert gated_tool_kernel.executed_count == 1


# ── CONFIRM camí WRITE_LOCAL: round-trip d'aprovació humà real ───────────────
def test_confirma_write_local_amb_aprovacio(bucle, make_session, orch,
                                            approval_gate, gated_tool_kernel):
    sess = make_session(role="operator")
    res = bucle.proposa(session=sess, text_nl="guardar nota",
                        params={"clau": "salutacio", "valor": "hola"})
    req = res.requests[0]
    # L'humà aprova (K6) → token.
    outcome = approval_gate.approve(request=req, approver_id="direccio")
    assert outcome.granted and outcome.token
    conf = bucle.confirma(session=sess, tasca_id=res.tasca.tasca_id, orchestrator=orch,
                          approvals={req.request_id: outcome.token})
    assert conf.executat is True
    assert conf.tasca.estat is EstatTasca.EXECUTADA
    assert gated_tool_kernel.executed_count == 1


# ── CONFIRM WRITE_LOCAL SENSE aprovació → escala, NO executa, segueix PROPOSADA ─
def test_confirma_sense_aprovacio_no_executa(bucle, make_session, orch, gated_tool_kernel):
    sess = make_session(role="operator")
    res = bucle.proposa(session=sess, text_nl="guardar nota",
                        params={"clau": "k", "valor": "v"})
    conf = bucle.confirma(session=sess, tasca_id=res.tasca.tasca_id, orchestrator=orch)
    assert conf.executat is False
    assert conf.run.escalated is True
    assert conf.tasca.estat is EstatTasca.PROPOSADA   # reintentable
    assert gated_tool_kernel.executed_count == 0


# ── Anti confused-deputy: una altra sessió no pot confirmar ──────────────────
def test_altra_sessio_no_confirma(bucle, make_session, orch):
    from app.errors import TascaError
    propietari = make_session(role="operator", session_id="sA", tenant="tA")
    res = bucle.proposa(session=propietari, text_nl="consultar document")
    intrus = make_session(role="operator", session_id="sB", tenant="tA")
    with pytest.raises(TascaError):
        bucle.confirma(session=intrus, tasca_id=res.tasca.tasca_id, orchestrator=orch)


# ── Token d'una acció no serveix per a una altra (re-materialització determinista) ─
def test_token_no_reutilitzable_entre_tasques(bucle, make_session, orch, approval_gate):
    sess = make_session(role="operator")
    a = bucle.proposa(session=sess, text_nl="guardar nota", params={"clau": "a", "valor": "1"})
    b = bucle.proposa(session=sess, text_nl="guardar nota", params={"clau": "b", "valor": "2"})
    # Aprova NOMÉS la tasca A.
    out = approval_gate.approve(request=a.requests[0], approver_id="direccio")
    # Intenta confirmar B amb el token i el request_id d'A → no casa amb l'acció de B.
    conf = bucle.confirma(session=sess, tasca_id=b.tasca.tasca_id, orchestrator=orch,
                          approvals={a.requests[0].request_id: out.token})
    assert conf.executat is False and conf.tasca.estat is EstatTasca.PROPOSADA


# ── Rebuig explícit d'una proposta ───────────────────────────────────────────
def test_rebutja_proposta(bucle, make_session):
    sess = make_session(role="operator")
    res = bucle.proposa(session=sess, text_nl="consultar document")
    t = bucle.rebutja(session=sess, tasca_id=res.tasca.tasca_id)
    assert t.estat is EstatTasca.REBUTJADA
