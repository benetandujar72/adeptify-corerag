"""K10 (F4) — Playbooks signats: càrrega/validació encreuada + instanciació segura.

La verificació GPG (amb pinning, G-D) es prova a test_allowlist.py (helper compartit);
aquí provem la lògica específica de playbooks amb verify=False, i instantiate() pur.
"""

from __future__ import annotations

import pytest

from app.allowlist import load_signed_allowlist
from app.errors import PlaybookError
from app.orchestrator import Plan
from app.playbooks import (
    Playbook,
    PlaybookParam,
    PlaybookStep,
    instantiate,
    load_signed_playbooks,
)
from app.risk import RiskLevel

AL = "/app/allowlist"


@pytest.fixture()
def allowlist():
    return load_signed_allowlist(
        data_path=f"{AL}/tools.yaml", sig_path=f"{AL}/tools.yaml.sig", pubkey_path=f"{AL}/pubkey.asc",
    )


def _yaml(tmp_path, contingut: str) -> str:
    f = tmp_path / "playbooks.yaml"
    f.write_text(contingut, encoding="utf-8")
    return str(f)


# ── K10.1 · Càrrega + validació encreuada contra l'allowlist ─────────────────
def test_carrega_playbook_ok(tmp_path, allowlist):
    path = _yaml(tmp_path, """
playbooks:
  - id: resum_doc
    descripcio: Llegeix un document sintetic
    risc_max: read
    params:
      - nom: doc_id
        tipus: str
        requerit: "true"
    passos:
      - tool_id: fs.read_synthetic
        args:
          doc_id: "{param:doc_id}"
      - tool_id: echo.info
        args:
          msg: hola
""")
    cat = load_signed_playbooks(
        data_path=path, sig_path="x", pubkey_path="x", allowlist=allowlist, verify=False,
    )
    assert "resum_doc" in cat
    pb = cat.require("resum_doc")
    assert pb.risc_max == RiskLevel.READ and pb.param("doc_id").tipus == "str"


def test_pas_amb_eina_fora_allowlist_rebutjat(tmp_path, allowlist):
    path = _yaml(tmp_path, """
playbooks:
  - id: dolent
    descripcio: x
    risc_max: read
    passos:
      - tool_id: evil.injected
""")
    with pytest.raises(PlaybookError):
        load_signed_playbooks(data_path=path, sig_path="x", pubkey_path="x",
                              allowlist=allowlist, verify=False)


def test_eina_supera_risc_max_rebutjat(tmp_path, allowlist):
    # Precondició: fs.read_synthetic té risc > info.
    assert allowlist.require("fs.read_synthetic").risk > RiskLevel.INFO
    path = _yaml(tmp_path, """
playbooks:
  - id: massa_risc
    descripcio: x
    risc_max: info
    passos:
      - tool_id: fs.read_synthetic
""")
    with pytest.raises(PlaybookError):
        load_signed_playbooks(data_path=path, sig_path="x", pubkey_path="x",
                              allowlist=allowlist, verify=False)


def test_placeholder_parcial_rebutjat(tmp_path, allowlist):
    path = _yaml(tmp_path, """
playbooks:
  - id: parcial
    descripcio: x
    risc_max: info
    params:
      - nom: t
        tipus: str
    passos:
      - tool_id: echo.info
        args:
          msg: "Resum de {param:t}"
""")
    with pytest.raises(PlaybookError):
        load_signed_playbooks(data_path=path, sig_path="x", pubkey_path="x",
                              allowlist=allowlist, verify=False)


def test_placeholder_param_no_declarat_rebutjat(tmp_path, allowlist):
    path = _yaml(tmp_path, """
playbooks:
  - id: noexist
    descripcio: x
    risc_max: info
    passos:
      - tool_id: echo.info
        args:
          msg: "{param:inexistent}"
""")
    with pytest.raises(PlaybookError):
        load_signed_playbooks(data_path=path, sig_path="x", pubkey_path="x",
                              allowlist=allowlist, verify=False)


# ── K10.2 · instantiate() determinista i segur ───────────────────────────────
def _pb(**kw) -> Playbook:
    base = dict(
        id="p", descripcio="",
        params=(PlaybookParam("doc_id", "str"),),
        passos=(PlaybookStep("fs.read_synthetic", {"doc_id": "{param:doc_id}"}),),
        risc_max=RiskLevel.READ,
    )
    base.update(kw)
    return Playbook(**base)


def test_instantiate_substitueix_exacte():
    plan = instantiate(_pb(), {"doc_id": "NOFC_2024"})
    assert isinstance(plan, Plan) and len(plan.steps) == 1
    assert plan.steps[0].tool_id == "fs.read_synthetic"
    assert plan.steps[0].args == {"doc_id": "NOFC_2024"}


def test_instantiate_param_requerit_falta():
    with pytest.raises(PlaybookError):
        instantiate(_pb(), {})


def test_instantiate_param_desconegut_rebutjat():
    with pytest.raises(PlaybookError):
        instantiate(_pb(), {"doc_id": "x", "extra": "y"})


def test_instantiate_pii_evident_rebutjada():
    with pytest.raises(PlaybookError):
        instantiate(_pb(), {"doc_id": "12345678Z"})  # DNI


def test_instantiate_tipus_incorrecte():
    pb = _pb(params=(PlaybookParam("n", "int"),),
             passos=(PlaybookStep("echo.info", {"msg": "{param:n}"}),))
    with pytest.raises(PlaybookError):
        instantiate(pb, {"n": "no-es-int"})


def test_instantiate_valor_param_no_es_re_templatitza():
    """INV-1: un valor de param que sembli un placeholder/codi NO es re-interpreta;
    arriba al Plan com a string literal, mai s'executa ni es torna a substituir."""
    plan = instantiate(_pb(), {"doc_id": "{param:doc_id}"})
    assert plan.steps[0].args["doc_id"] == "{param:doc_id}"  # literal, no recursió
