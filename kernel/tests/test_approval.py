"""F3 · K6.1/K6.2/K6.4 — L'humà al bucle: compuerta propose→approve.

Cobreix: política d'aprovació per nivell, resum NL determinista, request_id lligat
a l'acció, anti-fatiga, integració amb el kernel d'eines (acció ≥2 sense aprovació →
PENDING_APPROVAL; nivell 4 amb una sola aprovació no s'executa) i amb l'orquestrador.
"""

from __future__ import annotations

import dataclasses
import re
import time

import jwt
import pytest
from pydantic import BaseModel

from app.approval import (
    APPROVAL_DISABLED, APPROVAL_TYP, ApprovalRequest, approval_request_id,
    aprovacions_requerides, requereix_aprovacio, resum_natural,
)
from app.errors import (
    AllowlistError, ApprovalError, ApprovalRateLimited, ApprovalRequired, PolicyDenied,
)
from app.orchestrator import Orchestrator, Plan
from app.policy import AllowRule, PolicyEngine
from app.risk import RiskLevel
from app.tools import Tool, ToolKernel


# ── Helpers per a les regressions del red-team ──
class _KvArgs(BaseModel):
    key: str
    value: str


class _KvResult(BaseModel):
    ok: bool


def _kv_tool() -> Tool:
    return Tool("kv.put_local", RiskLevel.WRITE_LOCAL, _KvArgs, _KvResult,
                lambda a, c, x: {"ok": True})


def _op_policy() -> PolicyEngine:
    return PolicyEngine([AllowRule("operator", RiskLevel.WRITE_LOCAL)])


# ── Red-team F4: token single-use + grant idempotent/terminal ───────────────
def test_token_single_use(approval_gate, make_session):
    """Un token aprova UNA execució; reutilitzar-lo dins del TTL es rebutja (anti-replay)."""
    sess = make_session()
    req = approval_gate.propose(session=sess, tool_id="kv.put_local",
                                risk=RiskLevel.WRITE_LOCAL, args={"key": "k", "value": "v"})
    out = approval_gate.approve(request=req, approver_id="alice")
    assert out.granted and out.token
    kw = dict(request_id=req.request_id, tool_id="kv.put_local", session_id=sess.context.session_id)
    approval_gate.verify_token(out.token, **kw)            # 1a vegada: OK
    with pytest.raises(ApprovalError):
        approval_gate.verify_token(out.token, **kw)        # 2a vegada: rebuig (single-use)


def test_grant_idempotent_no_remint(approval_gate, make_session):
    """Aprovar un request JA concedit no re-encunya cap token nou (terminal)."""
    sess = make_session()
    req = approval_gate.propose(session=sess, tool_id="kv.put_local",
                                risk=RiskLevel.WRITE_LOCAL, args={"key": "k", "value": "v"})
    out1 = approval_gate.approve(request=req, approver_id="alice")
    assert out1.granted and out1.token
    out2 = approval_gate.approve(request=req, approver_id="alice")
    assert out2.granted and out2.token is None            # no re-mint
    assert req.request_id not in approval_gate._pending    # PENDING purgat


# ── Política d'aprovació per nivell (K6.1) ──
def test_aprovacions_requerides_per_nivell():
    assert aprovacions_requerides(RiskLevel.INFO) == 0
    assert aprovacions_requerides(RiskLevel.READ) == 0
    assert aprovacions_requerides(RiskLevel.WRITE_LOCAL) == 1
    assert aprovacions_requerides(RiskLevel.WRITE_EXTERNAL) == 1
    assert aprovacions_requerides(RiskLevel.IRREVERSIBLE) == 2  # doble validació


def test_requereix_aprovacio_a_partir_de_2():
    assert requereix_aprovacio(RiskLevel.INFO) is False
    assert requereix_aprovacio(RiskLevel.READ) is False
    assert requereix_aprovacio(RiskLevel.WRITE_LOCAL) is True
    assert requereix_aprovacio(RiskLevel.IRREVERSIBLE) is True


# ── request_id determinista i lligat a l'acció (K6.1, anti confused-deputy) ──
def test_request_id_determinista_i_sensible_als_args():
    base = dict(session_id="s1", tenant_id="tA", tool_id="kv.put_local", risk=2)
    a = approval_request_id(args={"key": "k", "value": "v"}, **base)
    b = approval_request_id(args={"key": "k", "value": "v"}, **base)
    c = approval_request_id(args={"key": "k", "value": "ALTRE"}, **base)
    d = approval_request_id(args={"key": "k", "value": "v"}, **{**base, "tool_id": "fs.delete_all"})
    assert a == b          # mateixos inputs → mateix id
    assert a != c          # args diferents → id diferent
    assert a != d          # eina diferent → id diferent
    assert len(a) == 64    # SHA-256 hex


# ── Resum en llenguatge natural (K6.2): ≤3 frases, sense valors ──
def test_resum_natural_tres_frases_i_reversibilitat():
    r = resum_natural(tool_id="kv.put_local", risk=RiskLevel.WRITE_LOCAL,
                      args={"key": "k", "value": "v"}, descripcio="Desa una clau-valor local")
    # frases acabades en punt seguit d'espai o final (no compta el punt de «kv.put_local»)
    assert len(re.findall(r"\.(\s|$)", r)) <= 3
    assert "write-local" in r
    assert "reversible" in r.lower()

    r4 = resum_natural(tool_id="fs.delete_all", risk=RiskLevel.IRREVERSIBLE, args={"confirm": True})
    assert "IRREVERSIBLE" in r4
    assert "no es pot desfer" in r4.lower()


def test_resum_no_filtra_valors_dels_args():
    """INV-5: el resum mostra els NOMS dels camps, mai els VALORS (poden ser sensibles)."""
    r = resum_natural(tool_id="kv.put_local", risk=RiskLevel.WRITE_LOCAL,
                      args={"key": "alumne_id_SECRET", "value": "nota_99"})
    assert "key" in r and "value" in r       # noms dels camps: sí
    assert "alumne_id_SECRET" not in r        # valors: mai
    assert "nota_99" not in r


# ── Compuerta propose→approve (K6.1) ──
def test_propose_deixa_pending_i_audita(approval_gate, audit, make_session):
    s = make_session(role="operator")
    req = approval_gate.propose(session=s, tool_id="kv.put_local",
                                risk=RiskLevel.WRITE_LOCAL, args={"key": "k", "value": "v"})
    assert isinstance(req, ApprovalRequest)
    assert req.aprovacions_requerides == 1
    assert any(e.action == "decision:PENDING_APPROVAL" for e in audit.entries)


def test_una_aprovacio_concedeix_per_risc_2(approval_gate, make_session):
    s = make_session(role="operator")
    req = approval_gate.propose(session=s, tool_id="kv.put_local",
                                risk=RiskLevel.WRITE_LOCAL, args={"key": "k", "value": "v"})
    out = approval_gate.approve(request=req, approver_id="prof1")
    assert out.granted is True
    assert out.token is not None
    assert out.recollides == 1 and out.requerides == 1


def test_nivell_4_necessita_dos_aprovadors_distints(approval_gate, make_session):
    """nivel 4 con una sola aprobación NO se ejecuta (K6.3 llavor: doble validació)."""
    s = make_session(role="superadmin")
    req = approval_gate.propose(session=s, tool_id="fs.delete_all",
                                risk=RiskLevel.IRREVERSIBLE, args={"confirm": True})
    out1 = approval_gate.approve(request=req, approver_id="prof1")
    assert out1.granted is False and out1.token is None      # 1/2 → encara pendent
    # el MATEIX humà no compta dues vegades
    out_dup = approval_gate.approve(request=req, approver_id="prof1")
    assert out_dup.granted is False and out_dup.recollides == 1
    # un SEGON aprovador distint → concedeix
    out2 = approval_gate.approve(request=req, approver_id="prof2")
    assert out2.granted is True and out2.token is not None
    assert out2.recollides == 2 and out2.requerides == 2


def test_approve_sense_proposta_falla(approval_gate, make_session):
    s = make_session(role="operator")
    fantasma = ApprovalRequest(
        request_id="0" * 64, session_id=s.context.session_id, tenant_id="tA",
        tool_id="kv.put_local", risk=2, resum="x", aprovacions_requerides=1, created_at=0.0,
    )
    with pytest.raises(ApprovalError):
        approval_gate.approve(request=fantasma, approver_id="prof1")


# ── Verificació del token (K6.1) ──
def test_token_valid_passa_verificacio(approval_gate, make_session):
    s = make_session(role="operator")
    args = {"key": "k", "value": "v"}
    req = approval_gate.propose(session=s, tool_id="kv.put_local",
                                risk=RiskLevel.WRITE_LOCAL, args=args)
    out = approval_gate.approve(request=req, approver_id="prof1")
    data = approval_gate.verify_token(out.token, request_id=req.request_id,
                                      tool_id="kv.put_local", session_id=s.context.session_id)
    assert data["typ"] == APPROVAL_TYP


def test_token_no_lliga_amb_altra_accio(approval_gate, make_session):
    s = make_session(role="operator")
    req = approval_gate.propose(session=s, tool_id="kv.put_local",
                                risk=RiskLevel.WRITE_LOCAL, args={"key": "k", "value": "v"})
    out = approval_gate.approve(request=req, approver_id="prof1")
    with pytest.raises(ApprovalError):  # request_id que no coincideix
        approval_gate.verify_token(out.token, request_id="f" * 64,
                                   tool_id="kv.put_local", session_id=s.context.session_id)
    with pytest.raises(ApprovalError):  # una altra eina
        approval_gate.verify_token(out.token, request_id=req.request_id,
                                   tool_id="fs.delete_all", session_id=s.context.session_id)
    with pytest.raises(ApprovalError):  # una altra sessió
        approval_gate.verify_token(out.token, request_id=req.request_id,
                                   tool_id="kv.put_local", session_id="ALTRA")


def test_token_caducat_rebutjat(approval_gate, make_session):
    s = make_session(role="operator")
    req = approval_gate.propose(session=s, tool_id="kv.put_local",
                                risk=RiskLevel.WRITE_LOCAL, args={"key": "k", "value": "v"})
    # _now=1.0 → exp ≈ epoch 1970 → caducat respecte al rellotge real.
    out = approval_gate.approve(request=req, approver_id="prof1", _now=1.0)
    with pytest.raises(ApprovalError):
        approval_gate.verify_token(out.token, request_id=req.request_id,
                                   tool_id="kv.put_local", session_id=s.context.session_id)


def test_token_falsificat_rebutjat(approval_gate, make_session):
    s = make_session(role="operator")
    forjat = jwt.encode(
        {"typ": APPROVAL_TYP, "request_id": "x", "tool_id": "kv.put_local",
         "session_id": s.context.session_id, "tenant_id": "tA", "risk_level": 2,
         "iss": "adeptify-kernel", "aud": "adeptify-approval",
         "iat": int(time.time()), "exp": int(time.time()) + 1000},
        "secret-equivocat-de-debo-no-real", algorithm="HS256",
    )
    with pytest.raises(ApprovalError):
        approval_gate.verify_token(forjat, request_id="x", tool_id="kv.put_local",
                                   session_id=s.context.session_id)


def test_capability_token_no_serveix_com_aprovacio(approval_gate, issuer, make_session):
    """Un capability token (audiència 'adeptify-tools') no val com a aprovació humana."""
    s = make_session(role="operator")
    cap = issuer.mint(tool_id="kv.put_local", session_id=s.context.session_id,
                      tenant_id="tA", risk_level=2)
    with pytest.raises(ApprovalError):
        approval_gate.verify_token(cap, request_id="x", tool_id="kv.put_local",
                                   session_id=s.context.session_id)


# ── Anti-fatiga (K6.4) ──
def _propose_n(gate, session, n):
    return [gate.propose(session=session, tool_id="kv.put_local", risk=RiskLevel.WRITE_LOCAL,
                         args={"key": f"k{i}", "value": "v"}) for i in range(n)]


def test_anti_fatiga_bloqueja_la_sisena_en_60s(approval_gate, audit, make_session):
    s = make_session(role="operator")
    reqs = _propose_n(approval_gate, s, 6)
    for i in range(5):  # 5 aprovacions dins la finestra → OK
        approval_gate.approve(request=reqs[i], approver_id="prof1", _now=1000.0 + i)
    with pytest.raises(ApprovalRateLimited):  # la 6a (>5/60s) → bloquejada
        approval_gate.approve(request=reqs[5], approver_id="prof1", _now=1000.0 + 5)
    assert any(e.action == "alert:approval_fatigue" for e in audit.entries)  # alerta admin


def test_anti_fatiga_finestra_lliscant(approval_gate, make_session):
    s = make_session(role="operator")
    reqs = _propose_n(approval_gate, s, 6)
    for i in range(5):
        approval_gate.approve(request=reqs[i], approver_id="prof2", _now=1000.0 + i)
    # molt després de la finestra (60s) → les antigues no compten → permet de nou
    out = approval_gate.approve(request=reqs[5], approver_id="prof2", _now=1200.0)
    assert out.granted is True


def test_anti_fatiga_cooldown_caduca(approval_gate, make_session):
    s = make_session(role="operator")
    reqs = _propose_n(approval_gate, s, 7)
    for i in range(5):
        approval_gate.approve(request=reqs[i], approver_id="prof3", _now=1000.0 + i)
    with pytest.raises(ApprovalRateLimited):  # dispara cooldown (300s) a t=1005
        approval_gate.approve(request=reqs[5], approver_id="prof3", _now=1005.0)
    with pytest.raises(ApprovalRateLimited):  # dins del cooldown
        approval_gate.approve(request=reqs[6], approver_id="prof3", _now=1100.0)
    # passat el cooldown (1005+300=1305) i la finestra → permet
    out = approval_gate.approve(request=reqs[6], approver_id="prof3", _now=1400.0)
    assert out.granted is True


# ── Integració amb el kernel d'eines (K6.1) ──
def test_accio_risc_2_sense_aprovacio_es_pending(gated_tool_kernel, make_session):
    """acción nivel 2 sin aprobación ⇒ PENDING_APPROVAL; no s'executa res."""
    s = make_session(role="operator")
    with pytest.raises(ApprovalRequired) as ei:
        gated_tool_kernel.invoke(session=s, tool_id="kv.put_local",
                                 args={"key": "k", "value": "v"})
    assert ei.value.request.tool_id == "kv.put_local"
    assert gated_tool_kernel.executed_count == 0


def test_accio_risc_2_amb_token_s_executa(gated_tool_kernel, approval_gate, make_session):
    s = make_session(role="operator")
    args = {"key": "k", "value": "v"}
    req = approval_gate.propose(session=s, tool_id="kv.put_local",
                                risk=RiskLevel.WRITE_LOCAL, args=args)
    tok = approval_gate.approve(request=req, approver_id="prof1").token
    res = gated_tool_kernel.invoke(session=s, tool_id="kv.put_local", args=args, approval_token=tok)
    assert res.ok is True
    assert gated_tool_kernel.executed_count == 1


def test_token_d_altra_accio_no_executa(gated_tool_kernel, approval_gate, make_session):
    """Confused-deputy: un token aprovat per l'acció A no executa l'acció B."""
    s = make_session(role="operator")
    req_a = approval_gate.propose(session=s, tool_id="kv.put_local",
                                  risk=RiskLevel.WRITE_LOCAL, args={"key": "a", "value": "1"})
    tok_a = approval_gate.approve(request=req_a, approver_id="prof1").token
    with pytest.raises(ApprovalError):
        gated_tool_kernel.invoke(session=s, tool_id="kv.put_local",
                                 args={"key": "b", "value": "2"}, approval_token=tok_a)
    assert gated_tool_kernel.executed_count == 0


def test_nivell_4_una_aprovacio_no_executa(gated_tool_kernel, approval_gate, make_session):
    s = make_session(role="superadmin")
    args = {"confirm": True}
    req = approval_gate.propose(session=s, tool_id="fs.delete_all",
                                risk=RiskLevel.IRREVERSIBLE, args=args)
    out1 = approval_gate.approve(request=req, approver_id="prof1")  # 1/2
    assert out1.token is None
    with pytest.raises(ApprovalRequired):  # sense token → no s'executa
        gated_tool_kernel.invoke(session=s, tool_id="fs.delete_all", args=args)
    assert gated_tool_kernel.executed_count == 0
    # segona aprovació distinta → token → ja s'executa
    tok = approval_gate.approve(request=req, approver_id="prof2").token
    res = gated_tool_kernel.invoke(session=s, tool_id="fs.delete_all", args=args, approval_token=tok)
    assert res.deleted == 0
    assert gated_tool_kernel.executed_count == 1


def test_inv2_rbac_abans_que_aprovacio(gated_tool_kernel, make_session):
    """INV-2: un rol baix és bloquejat pel RBAC (PolicyDenied), no pel gate d'aprovació.
    L'aprovació MAI eludeix el RBAC."""
    s = make_session(role="viewer")
    with pytest.raises(PolicyDenied):
        gated_tool_kernel.invoke(session=s, tool_id="kv.put_local",
                                 args={"key": "k", "value": "v"})
    assert gated_tool_kernel.executed_count == 0


def test_risc_baix_no_requereix_aprovacio(gated_tool_kernel, make_session):
    """Risc <2 s'executa sense cap aprovació, encara que hi hagi gate."""
    s = make_session(role="viewer")
    res = gated_tool_kernel.invoke(session=s, tool_id="fs.read_synthetic", args={"doc_id": "d1"})
    assert res.content
    assert gated_tool_kernel.executed_count == 1


def test_cierre_auditoria_k92(gated_tool_kernel, approval_gate, audit, make_session):
    """K9.2: el cicle propose→approve→execute deixa traça PENDING/APPROVED/EXECUTED
    i la cadena d'auditoria segueix verificable."""
    s = make_session(role="operator")
    args = {"key": "k", "value": "v"}
    req = approval_gate.propose(session=s, tool_id="kv.put_local",
                                risk=RiskLevel.WRITE_LOCAL, args=args)
    tok = approval_gate.approve(request=req, approver_id="prof1").token
    gated_tool_kernel.invoke(session=s, tool_id="kv.put_local", args=args, approval_token=tok)
    actions = [e.action for e in audit.entries]
    assert "decision:PENDING_APPROVAL" in actions
    assert "decision:APPROVED" in actions
    assert "decision:EXECUTED" in actions
    assert audit.verify() is True


# ── Integració amb l'orquestrador (l'humà al bucle) ──
def test_orchestrator_escala_si_cal_aprovacio(gated_tool_kernel, make_session):
    s = make_session(role="operator")
    orch = Orchestrator(gated_tool_kernel)
    plan = Plan.from_list([{"tool_id": "kv.put_local", "args": {"key": "k", "value": "v"}}])
    res = orch.run(s, plan)
    assert res.escalated is True
    assert "PENDING_APPROVAL" in (res.escalation_reason or "")
    assert gated_tool_kernel.executed_count == 0


def test_orchestrator_executa_amb_aprovacio(gated_tool_kernel, approval_gate, make_session):
    s = make_session(role="operator")
    args = {"key": "k", "value": "v"}
    req = approval_gate.propose(session=s, tool_id="kv.put_local",
                                risk=RiskLevel.WRITE_LOCAL, args=args)
    tok = approval_gate.approve(request=req, approver_id="prof1").token
    orch = Orchestrator(gated_tool_kernel)
    plan = Plan.from_list([{"tool_id": "kv.put_local", "args": args}])
    res = orch.run(s, plan, approvals={req.request_id: tok})
    assert res.completed is True and res.executed_ok == 1
    assert gated_tool_kernel.executed_count == 1


# ── Regressions del red-team F3-CORE (3 troballes confirmades, ara tancades) ──
def test_redteam1_fail_closed_sense_gate(allowlist, issuer, make_session):
    """#1 skip-the-gate: SENSE compuerta (defecte), una acció de risc ≥2 NO s'executa
    (fail-closed), encara que el RBAC la permeti."""
    tk = ToolKernel(allowlist=allowlist, policy=_op_policy(), issuer=issuer)  # gate per defecte
    tk.register(_kv_tool())
    s = make_session(role="operator")
    with pytest.raises(ApprovalError):
        tk.invoke(session=s, tool_id="kv.put_local", args={"key": "k", "value": "v"})
    assert tk.executed_count == 0


def test_redteam1_opt_out_explicit_executa(allowlist, issuer, make_session):
    """#1: l'opt-out EXPLÍCIT (APPROVAL_DISABLED) sí executa risc ≥2 sense token
    (mode F1/F2 conscient i auditable)."""
    tk = ToolKernel(allowlist=allowlist, policy=_op_policy(), issuer=issuer,
                    approval_gate=APPROVAL_DISABLED)
    tk.register(_kv_tool())
    s = make_session(role="operator")
    res = tk.invoke(session=s, tool_id="kv.put_local", args={"key": "k", "value": "v"})
    assert res.ok is True and tk.executed_count == 1


def test_redteam2_aprovador_normalitzat_no_falseja_distincio(approval_gate, make_session):
    """#2 double-approval: variants de majúscules/espais del MATEIX humà no compten
    com a aprovadors distints (no es satisfà la doble validació de nivell 4)."""
    s = make_session(role="superadmin")
    req = approval_gate.propose(session=s, tool_id="fs.delete_all",
                                risk=RiskLevel.IRREVERSIBLE, args={"confirm": True})
    approval_gate.approve(request=req, approver_id="Alice")
    approval_gate.approve(request=req, approver_id="  alice ")
    out3 = approval_gate.approve(request=req, approver_id="ALICE")
    assert out3.granted is False and out3.recollides == 1  # tot col·lapsa a 1 humà
    out4 = approval_gate.approve(request=req, approver_id="Bob")  # segon humà real
    assert out4.granted is True and out4.recollides == 2


def test_redteam2_aprovador_buit_o_invalid_rebutjat(approval_gate, make_session):
    """#2: identificador d'aprovador buit/espais/None/no-cadena → rebutjat."""
    s = make_session(role="operator")
    req = approval_gate.propose(session=s, tool_id="kv.put_local",
                                risk=RiskLevel.WRITE_LOCAL, args={"key": "k", "value": "v"})
    for dolent in ["", "   ", None, 123]:
        with pytest.raises(ApprovalError):
            approval_gate.approve(request=req, approver_id=dolent)


def test_redteam3_tool_es_immutable():
    """#3 INV-4: una eina registrada és immutable; no es pot substituir la seva `fn`
    després de l'aprovació."""
    t = _kv_tool()
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.fn = lambda a, c, x: {"ok": False}  # type: ignore[misc]


def test_redteam3_no_reescriptura_eina_registrada(allowlist, issuer):
    """#3: registrar dues vegades la mateixa eina (anti-swap) → rebutjat."""
    tk = ToolKernel(allowlist=allowlist, policy=_op_policy(), issuer=issuer,
                    approval_gate=APPROVAL_DISABLED)
    tk.register(_kv_tool())
    with pytest.raises(AllowlistError):
        tk.register(_kv_tool())
