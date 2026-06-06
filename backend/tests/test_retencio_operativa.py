"""Tests de retenció dry-run i control MFA de producció."""

from __future__ import annotations

import datetime as dt


def _seed(db):
    from app.core import users
    from app.db.models import Institucio

    db.add(Institucio(slug="inst_ret", nom="Centre Retenció", actiu=True))
    db.commit()
    users.crea_usuari(db, "dir_ret", "k", "direccio", institucio_id="inst_ret")
    users.crea_usuari(db, "doc_ret", "k", "docent", institucio_id="inst_ret")
    db.commit()


def _login(client, usuari: str) -> str:
    resp = client.post(
        "/api/auth/login",
        json={"usuari": usuari, "contrasenya": "k", "institucio": "inst_ret"},
    )
    assert resp.status_code == 200
    return resp.json()["token"]


def test_retencio_endpoint_dry_run_i_rbac(client, db):
    _seed(db)
    from app.db.models import Conversation

    vell = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=500)
    conv = Conversation(
        id="conv_vella",
        titol="Conversa antiga",
        agent_id="secretaria",
        institucio_id="inst_ret",
        usuari="dir_ret",
        rol="direccio",
        creat_el=vell,
        actualitzat_el=vell,
    )
    db.add(conv)
    db.commit()

    token_doc = _login(client, "doc_ret")
    token_dir = _login(client, "dir_ret")
    assert client.get(
        "/api/system/retencio",
        headers={"Authorization": f"Bearer {token_doc}"},
    ).status_code == 403

    resp = client.get(
        "/api/system/retencio",
        headers={"Authorization": f"Bearer {token_dir}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "dry-run"
    assert body["candidates"]["converses"] >= 1
    # Dry-run: no ha esborrat la conversa candidata.
    assert db.get(Conversation, "conv_vella") is not None


def test_produccio_check_avisa_mfa_gestors(client, db):
    _seed(db)
    token_dir = _login(client, "dir_ret")
    resp = client.get(
        "/api/system/produccio",
        headers={"Authorization": f"Bearer {token_dir}"},
    )
    assert resp.status_code == 200
    controls = {c["clau"]: c for c in resp.json()["controls"]}
    assert "mfa_gestors" in controls
    assert controls["mfa_gestors"]["severitat"] in {"avis", "ok", "info"}


def test_arsul_export_sense_secrets_i_amb_aillament(client, db):
    _seed(db)
    from app.core import users
    from app.db.models import AuditLog, Conversation, Feedback, Institucio, Message, User

    db.add(Institucio(slug="inst_alt", nom="Centre Alternatiu", actiu=True))
    users.crea_usuari(db, "doc_ret", "k2", "docent", institucio_id="inst_alt")
    token_doc = _login(client, "doc_ret")
    token_dir = _login(client, "dir_ret")

    target = db.query(User).filter_by(username="doc_ret", institucio_id="inst_ret").one()
    target.totp_secret = "SECRET-NO-EXPORTAR"
    target.totp_actiu = True

    ara = dt.datetime.now(dt.timezone.utc)
    conv = Conversation(
        id="conv_arsul",
        titol="Conversa ARSUL",
        agent_id="secretaria",
        institucio_id="inst_ret",
        usuari="doc_ret",
        rol="docent",
        creat_el=ara,
        actualitzat_el=ara,
    )
    conv_alt = Conversation(
        id="conv_alt",
        titol="Conversa aliena",
        agent_id="secretaria",
        institucio_id="inst_alt",
        usuari="doc_ret",
        rol="docent",
        creat_el=ara,
        actualitzat_el=ara,
    )
    db.add_all([conv, conv_alt])
    db.add(
        Message(
            conversation_id="conv_arsul",
            rol="user",
            contingut="Vull exercir el dret d'acces.",
            agent_id="secretaria",
            creat_el=ara,
        )
    )
    db.add(
        Feedback(
            message_id="msg_1",
            valor="util",
            comentari="Correcte",
            usuari="doc_ret",
            institucio_id="inst_ret",
            creat_el=ara,
        )
    )
    db.add_all(
        [
            AuditLog(
                usuari="doc_ret",
                rol="docent",
                accio="chat",
                conversation_id="conv_arsul",
                detalls={"ok": True},
                creat_el=ara,
            ),
            AuditLog(
                usuari="doc_ret",
                rol="docent",
                accio="chat",
                conversation_id="conv_alt",
                detalls={"leak": True},
                creat_el=ara,
            ),
        ]
    )
    db.commit()

    assert client.get(
        "/api/system/arsul/export",
        params={"usuari_objectiu": "doc_ret"},
        headers={"Authorization": f"Bearer {token_doc}"},
    ).status_code == 403
    assert client.get(
        "/api/system/arsul/export",
        params={"usuari_objectiu": "doc_ret", "institucio": "inst_alt"},
        headers={"Authorization": f"Bearer {token_dir}"},
    ).status_code == 403

    resp = client.get(
        "/api/system/arsul/export",
        params={"usuari_objectiu": "doc_ret"},
        headers={"Authorization": f"Bearer {token_dir}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["subject"] == {"username": "doc_ret", "institucio_id": "inst_ret"}
    assert body["profile"]["mfa_actiu"] is True
    assert "password_hash" not in body["profile"]
    assert "totp_secret" not in body["profile"]
    assert "SECRET-NO-EXPORTAR" not in str(body)
    assert body["summary"]["converses"] == 1
    assert body["summary"]["missatges"] == 1
    assert body["summary"]["feedback"] == 1
    assert [c["id"] for c in body["conversations"]] == ["conv_arsul"]
    assert [a["conversation_id"] for a in body["audit_log"]] == ["conv_arsul"]
    assert body["limitacions"]
