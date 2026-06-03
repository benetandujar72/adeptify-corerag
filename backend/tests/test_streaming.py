"""Tests de l'streaming SSE de POST /api/chat (stream=true)."""

from __future__ import annotations

import json


def _parse_sse(text: str) -> list[tuple[str, str]]:
    """Parseig mínim d'un flux SSE en parelles (event, data)."""
    esdeveniments = []
    event = None
    for linia in text.splitlines():
        if linia.startswith("event:"):
            event = linia[len("event:"):].strip()
        elif linia.startswith("data:"):
            data = linia[len("data:"):].strip()
            esdeveniments.append((event or "message", data))
    return esdeveniments


def test_chat_stream_emet_events(client, auth, document_indexat):
    resp = client.post(
        "/api/chat",
        headers=auth,
        json={"agent_id": "secretaria", "message": "Quan és l'esquí?", "stream": True},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    tipus = [e for e, _ in events]
    assert "sources" in tipus
    assert "token" in tipus
    assert "done" in tipus

    # 'sources' és un array de fonts.
    fonts_data = next(d for e, d in events if e == "sources")
    fonts = json.loads(fonts_data)
    assert isinstance(fonts, list)

    # 'done' conté el Message final amb agent_utilitzat.
    done_data = next(d for e, d in events if e == "done")
    done = json.loads(done_data)
    assert "message" in done
    assert "agent_utilitzat" in done
    assert done["message"]["rol"] == "assistant"
