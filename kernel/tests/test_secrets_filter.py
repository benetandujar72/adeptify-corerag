"""K8.3 — filtre de secrets abans del context (INV-5).

Els "secrets" són FALSOS i es construeixen en temps d'execució (concatenació) perquè
el FITXER no contingui cap patró literal de secret (gitleaks net), mentre el test sí
valida la detecció/redacció sobre la cadena construïda.
"""

from __future__ import annotations

from app.secrets_filter import REDACTION, context_es_net, redact_secrets, scan_secrets

FAKE_OPENAI = "sk-" + "A" * 24                       # patró sk-... (fals)
FAKE_PRIV = "-----BEGIN RSA PRIVATE " + "KEY-----\nMIIE...\n-----END"
FAKE_ASSIGN = "password: " + "hunter2-super-secret-value"
FAKE_TOKEN = "token=" + "abcdef0123456789xyz"


def test_redacta_openai_key_i_registra():
    """Un fragment RAG amb patró de clau (sk-...) es redacta ABANS d'injectar-se."""
    chunk = f"Notes del centre. La clau és {FAKE_OPENAI} i res més."
    net, findings = redact_secrets(chunk)
    assert FAKE_OPENAI not in net
    assert REDACTION in net
    assert any(f.tipus == "openai_key" for f in findings)  # queda registrat (tipus)


def test_redacta_assignacio_mante_clau():
    net, findings = redact_secrets(FAKE_ASSIGN)
    assert "hunter2-super-secret-value" not in net
    assert "password" in net.lower() and REDACTION in net
    assert any(f.tipus == "assignacio" for f in findings)


def test_redacta_clau_privada():
    net, _ = redact_secrets(FAKE_PRIV)
    assert "BEGIN RSA PRIVATE KEY" not in net


def test_context_net():
    assert context_es_net("Quin horari fa el menjador?") is True
    assert context_es_net(FAKE_TOKEN) is False


def test_scan_no_filtra_text_normal():
    assert scan_secrets("Resum del PEC i del NOFC del centre.") == []
