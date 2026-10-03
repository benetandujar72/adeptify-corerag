"""Tests del contracte d'API (TestClient): forma de resposta dels endpoints."""

from __future__ import annotations


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["estat"] == "ok"


def test_login_emet_token(client, db):
    # Des de la Fase 6 el login exigeix contrasenya (PBKDF2). Sembrem un usuari
    # i ens hi autentiquem amb la seva contrasenya.
    from app.core import users

    users.crea_usuari(db, "marta", "patufet2026", "docent", nom="Marta")
    db.commit()
    resp = client.post(
        "/api/auth/login", json={"usuari": "marta", "contrasenya": "patufet2026"}
    )
    assert resp.status_code == 200
    cos = resp.json()
    assert cos["rol"] == "docent"
    assert isinstance(cos["token"], str) and cos["token"]


def test_login_rol_invalid(client):
    resp = client.post("/api/auth/login", json={"usuari": "x", "rol": "hacker"})
    assert resp.status_code == 400
    assert resp.json()["error"]["codi"] == "BAD_REQUEST"


def test_me(client, token_docent):
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_docent}"})
    assert resp.status_code == 200
    cos = resp.json()
    assert cos["usuari"] == "marta"
    assert cos["rol"] == "docent"
    # Idioma per defecte: català (afegit a MeResponse amb i18n).
    assert cos.get("idioma") == "ca"


def test_me_sense_token(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["codi"] == "FORBIDDEN"


def test_agents_estructura(client, auth):
    resp = client.get("/api/agents", headers=auth)
    assert resp.status_code == 200
    agents = resp.json()["agents"]
    assert len(agents) >= 1
    a = agents[0]
    assert {"id", "nom", "descripcio", "color", "rols_permesos"} <= set(a.keys())


def test_agents_inclou_copilot_didactic_per_docent(client, auth):
    resp = client.get("/api/agents", headers=auth)
    assert resp.status_code == 200
    agents = {a["id"]: a for a in resp.json()["agents"]}
    assert "copilot_didactic" in agents
    assert agents["copilot_didactic"]["nom"] == "Copilot didàctic"
    assert "docent" in agents["copilot_didactic"]["rols_permesos"]
    assert "copilot_exercicis" in agents
    assert "copilot_adaptacions" in agents
    assert "copilot_butlleti" in agents


def test_system_status_estructura_i_crides_externes_zero(client, auth):
    # /system/status requereix autenticació (exposa host/model/entorn).
    assert client.get("/api/system/status").status_code == 401
    resp = client.get("/api/system/status", headers=auth)
    assert resp.status_code == 200
    cos = resp.json()
    assert set(cos.keys()) == {
        "servidor",
        "indexacio",
        "privadesa",
        "model",
        "versio",
    }
    assert cos["privadesa"]["crides_externes"] == 0
    assert cos["privadesa"]["processament_local"] is True


def test_chat_no_stream_format(client, auth, document_indexat):
    resp = client.post(
        "/api/chat",
        headers=auth,
        json={"agent_id": "secretaria", "message": "Quan és el curs d'esquí?", "stream": False},
    )
    assert resp.status_code == 200
    cos = resp.json()
    assert {"conversation_id", "message", "agent_utilitzat"} <= set(cos.keys())
    msg = cos["message"]
    assert msg["rol"] == "assistant"
    assert msg["agent_id"] == cos["agent_utilitzat"]
    assert isinstance(msg["fonts"], list)
    assert msg["confianca"] is not None
    # La font ha de citar el document indexat.
    assert any(f["doc_id"] == "nofc_2024" for f in msg["fonts"])


def test_conversa_es_crea_i_es_recupera(client, auth, document_indexat):
    r1 = client.post(
        "/api/chat",
        headers=auth,
        json={"agent_id": "secretaria", "message": "Quan és l'esquí?", "stream": False},
    )
    conv_id = r1.json()["conversation_id"]

    r2 = client.get("/api/conversations", headers=auth)
    assert r2.status_code == 200
    assert any(c["id"] == conv_id for c in r2.json()["conversations"])

    r3 = client.get(f"/api/conversations/{conv_id}", headers=auth)
    assert r3.status_code == 200
    msgs = r3.json()["messages"]
    # user + assistant
    assert len(msgs) >= 2
    assert msgs[0]["rol"] == "user"


def test_delete_conversa(client, auth, document_indexat):
    r1 = client.post(
        "/api/chat",
        headers=auth,
        json={"agent_id": "secretaria", "message": "Hola", "stream": False},
    )
    conv_id = r1.json()["conversation_id"]
    r2 = client.delete(f"/api/conversations/{conv_id}", headers=auth)
    assert r2.status_code == 204
    r3 = client.get(f"/api/conversations/{conv_id}", headers=auth)
    assert r3.status_code == 404


def test_documents_llista(client, auth, document_indexat):
    resp = client.get("/api/documents", headers=auth)
    assert resp.status_code == 200
    docs = resp.json()["documents"]
    assert any(d["doc_id"] == "nofc_2024" for d in docs)
    d = docs[0]
    assert {"doc_id", "filename", "tipus", "fragments", "estat"} <= set(d.keys())


def test_feedback(client, auth, db):
    from app.db.models import Conversation, Message
    conv = Conversation(agent_id="secretaria", usuari="marta", rol="docent")
    db.add(conv)
    db.flush()
    db.add(Message(id="msg_x", conversation_id=conv.id, rol="assistant", contingut="Resposta sintètica."))
    db.commit()
    resp = client.post(
        "/api/feedback",
        headers=auth,
        json={"message_id": "msg_x", "valor": "util", "comentari": "Molt clar"},
    )
    assert resp.status_code == 204


def test_conversa_no_trobada(client, auth):
    resp = client.get("/api/conversations/inexistent", headers=auth)
    assert resp.status_code == 404
    assert resp.json()["error"]["codi"] == "NOT_FOUND"
