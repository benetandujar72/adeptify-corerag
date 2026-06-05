"""K13·F5a — Resolutor d'intenció NL→playbook_id: ENUM tancat, determinista, fail-closed."""

from __future__ import annotations

import pytest

from app.allowlist import load_signed_allowlist
from app.intent import IntentResolver
from app.playbooks import load_signed_playbooks

AL = "/app/allowlist"

_PLAYBOOKS_YAML = """
playbooks:
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
  - id: exporta_csv
    descripcio: Exporta dades en format CSV
    alias:
      - exporta csv
    risc_max: read
    passos:
      - tool_id: fs.read_synthetic
        args:
          doc_id: "informe"
  - id: exporta_pdf
    descripcio: Exporta dades en format PDF
    alias:
      - exporta pdf
    risc_max: read
    passos:
      - tool_id: fs.read_synthetic
        args:
          doc_id: "informe"
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
def resolver(catalog):
    return IntentResolver(catalog)


# ── L'alias forma part de l'artefacte signat (es parseja al catàleg) ──────────
def test_alias_es_parseja_al_catalog(catalog):
    assert catalog.require("desa_nota").alias == ("guardar nota", "desa apunt")
    # Playbook sense alias declarat → tupla buida (retrocompatible amb F4).
    assert catalog.require("exporta_csv").alias == ("exporta csv",)


# ── Coincidència clara per alias / id ────────────────────────────────────────
def test_match_clar_per_alias(resolver):
    r = resolver.resol("vull guardar una nota al quadern")
    assert r.match == "desa_nota" and not r.ambigu and not r.refusat_pii


def test_match_clar_desambigua_csv_vs_pdf(resolver):
    r = resolver.resol("exporta el csv si us plau")
    assert r.match == "exporta_csv"
    # El segon candidat (exporta_pdf) hi és, però amb menys puntuació.
    assert r.candidates[0].playbook_id == "exporta_csv"
    assert r.candidates[0].score > r.candidates[1].score


def test_normalitzacio_accents_i_majuscules(resolver):
    # "Exportà" (accent) + majúscules ha de coincidir igual que "exporta".
    r = resolver.resol("EXPORTÀ el CSV")
    assert r.match == "exporta_csv"


# ── Fail-closed davant l'ambigüitat (empat) ──────────────────────────────────
def test_empat_es_ambigu_no_endevina(resolver):
    r = resolver.resol("exporta")  # encerta «exporta» a CSV i PDF per igual
    assert r.match is None and r.ambigu is True
    ids = {c.playbook_id for c in r.candidates}
    assert {"exporta_csv", "exporta_pdf"} <= ids
    # Mateixa puntuació → empat real.
    assert r.candidates[0].score == r.candidates[1].score


# ── Cap coincidència → match None, NO ambigu, sense candidats ─────────────────
def test_cap_coincidencia(resolver):
    r = resolver.resol("quin temps fa demà a la lluna")
    assert r.match is None and r.ambigu is False and r.candidates == ()


def test_text_buit(resolver):
    assert resolver.resol("   ").match is None
    assert resolver.resol("").match is None


# ── Frontera PII (G-I): es rebutja text amb PII evident ──────────────────────
@pytest.mark.parametrize("text", [
    "guardar nota de l'alumne amb DNI 12345678Z",
    "exporta csv i envia a pare@exemple.cat",
    "desa apunt del telèfon 600123456",
])
def test_refusa_pii_evident(resolver, text):
    r = resolver.resol(text)
    assert r.match is None and r.refusat_pii is True


# ── Propietat clau: la sortida SEMPRE és del catàleg (ENUM tancat, INV-4) ─────
def test_sortida_sempre_dins_del_catalog(resolver, catalog):
    entrades = [
        "guardar nota", "exporta csv", "exporta pdf", "exporta", "hola món",
        "desa apunt important", "", "PDF export now",
    ]
    for txt in entrades:
        r = resolver.resol(txt)
        assert r.match is None or r.match in catalog.ids
        for c in r.candidates:
            assert c.playbook_id in catalog.ids


def test_resolutor_es_determinista(resolver):
    a = resolver.resol("exporta el csv")
    b = resolver.resol("exporta el csv")
    assert a == b
