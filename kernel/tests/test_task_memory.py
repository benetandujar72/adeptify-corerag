"""K14·F5b — Memòria de tasques: màquina d'estats fail-closed + propietari + PII."""

from __future__ import annotations

import pytest

from app.errors import TascaError
from app.task_memory import EstatTasca, MemoriaTasques, tasca_id


@pytest.fixture()
def memoria():
    return MemoriaTasques()


# ── Registre + idempotència ──────────────────────────────────────────────────
def test_registra_proposta(memoria, make_session):
    sess = make_session()
    t = memoria.registra_proposta(session=sess, playbook_id="desa_nota",
                                  params={"clau": "c", "valor": "v"}, _now=1000.0)
    assert t.estat is EstatTasca.PROPOSADA
    assert t.playbook_id == "desa_nota" and t.params == {"clau": "c", "valor": "v"}
    assert t.creada_utc == 1000.0 and t.actualitzada_utc == 1000.0
    assert memoria.get(t.tasca_id) == t


def test_reproposta_pendent_es_idempotent(memoria, make_session):
    sess = make_session()
    a = memoria.registra_proposta(session=sess, playbook_id="p", params={"x": "1"})
    b = memoria.registra_proposta(session=sess, playbook_id="p", params={"x": "1"})
    assert a.tasca_id == b.tasca_id
    assert len(memoria.llista()) == 1  # no s'ha duplicat


def test_id_determinista_i_distint_per_params(make_session):
    s = make_session(session_id="s1", tenant="tA")
    base = dict(session_id="s1", tenant_id="tA", playbook_id="p")
    assert tasca_id(**base, params={"x": "1"}) == tasca_id(**base, params={"x": "1"})
    assert tasca_id(**base, params={"x": "1"}) != tasca_id(**base, params={"x": "2"})


# ── Cicle de vida feliç ──────────────────────────────────────────────────────
def test_propose_confirm_execute(memoria, make_session):
    sess = make_session()
    t = memoria.registra_proposta(session=sess, playbook_id="p", params={})
    c = memoria.confirma(t.tasca_id, session=sess, _now=2000.0)
    assert c.estat is EstatTasca.CONFIRMADA and c.actualitzada_utc == 2000.0
    e = memoria.marca_executada(t.tasca_id, session=sess)
    assert e.estat is EstatTasca.EXECUTADA and e.terminal is True


def test_rebuig(memoria, make_session):
    sess = make_session()
    t = memoria.registra_proposta(session=sess, playbook_id="p", params={})
    r = memoria.rebutja(t.tasca_id, session=sess)
    assert r.estat is EstatTasca.REBUTJADA and r.terminal is True


# ── Transicions il·legals (fail-closed) ──────────────────────────────────────
def test_no_executa_sense_confirmar(memoria, make_session):
    sess = make_session()
    t = memoria.registra_proposta(session=sess, playbook_id="p", params={})
    with pytest.raises(TascaError):
        memoria.marca_executada(t.tasca_id, session=sess)  # PROPOSADA→EXECUTADA prohibit


def test_no_reobre_terminal(memoria, make_session):
    sess = make_session()
    t = memoria.registra_proposta(session=sess, playbook_id="p", params={})
    memoria.rebutja(t.tasca_id, session=sess)
    with pytest.raises(TascaError):
        memoria.confirma(t.tasca_id, session=sess)  # REBUTJADA→CONFIRMADA prohibit


def test_no_reconfirma_executada(memoria, make_session):
    sess = make_session()
    t = memoria.registra_proposta(session=sess, playbook_id="p", params={})
    memoria.confirma(t.tasca_id, session=sess)
    memoria.marca_executada(t.tasca_id, session=sess)
    with pytest.raises(TascaError):
        memoria.confirma(t.tasca_id, session=sess)


def test_reproposta_decidida_es_rebutja(memoria, make_session):
    sess = make_session()
    t = memoria.registra_proposta(session=sess, playbook_id="p", params={"x": "1"})
    memoria.confirma(t.tasca_id, session=sess)
    with pytest.raises(TascaError):  # mateix id, ja decidida → no es reobre
        memoria.registra_proposta(session=sess, playbook_id="p", params={"x": "1"})


# ── Anti confused-deputy: només el propietari fa transicions ──────────────────
def test_altra_sessio_no_pot_confirmar(memoria, make_session):
    propietari = make_session(session_id="sA", tenant="tA")
    t = memoria.registra_proposta(session=propietari, playbook_id="p", params={})
    intrus = make_session(session_id="sB", tenant="tA")
    with pytest.raises(TascaError):
        memoria.confirma(t.tasca_id, session=intrus)


def test_altre_tenant_no_pot_confirmar(memoria, make_session):
    propietari = make_session(session_id="sA", tenant="tA")
    t = memoria.registra_proposta(session=propietari, playbook_id="p", params={})
    altre_tenant = make_session(session_id="sA", tenant="tB")  # mateixa sessió, altre tenant
    with pytest.raises(TascaError):
        memoria.confirma(t.tasca_id, session=altre_tenant)


# ── Frontera PII (G-I) ───────────────────────────────────────────────────────
@pytest.mark.parametrize("params", [
    {"dni": "12345678Z"},
    {"correu": "pare@exemple.cat"},
    {"tel": "600123456"},
])
def test_rebutja_pii_als_params(memoria, make_session, params):
    sess = make_session()
    with pytest.raises(TascaError):
        memoria.registra_proposta(session=sess, playbook_id="p", params=params)


# ── Llista filtrada per estat ────────────────────────────────────────────────
def test_llista_per_estat(memoria, make_session):
    sess = make_session()
    a = memoria.registra_proposta(session=sess, playbook_id="p", params={"x": "1"})
    b = memoria.registra_proposta(session=sess, playbook_id="p", params={"x": "2"})
    memoria.confirma(b.tasca_id, session=sess)
    pendents = memoria.llista(estat=EstatTasca.PROPOSADA)
    confirmades = memoria.llista(estat=EstatTasca.CONFIRMADA)
    assert [t.tasca_id for t in pendents] == [a.tasca_id]
    assert [t.tasca_id for t in confirmades] == [b.tasca_id]


def test_transicio_tasca_inexistent(memoria, make_session):
    with pytest.raises(TascaError):
        memoria.confirma("no-existeix", session=make_session())
