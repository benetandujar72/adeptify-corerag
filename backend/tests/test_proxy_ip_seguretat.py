"""Proves sintètiques de la identitat IP a la frontera del reverse proxy."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request

from app.core.roles import Rol
from app.core.security import acces_es_remot, comprova_acces_remot, ip_de_peticio

AUTENTICACIO_REAL = True  # cap adaptador de peer/identitat a aquestes regressions


def _request(peer, xff=None):
    headers = [] if xff is None else [(b"x-forwarded-for", xff.encode())]
    return Request({"type": "http", "headers": headers, "client": (peer, 12345)})


def _settings(enabled=True, trusted="172.30.0.2/32,172.30.0.3/32"):
    return SimpleNamespace(proxy_de_confianca=enabled, proxy_trusted_cidrs=trusted,
                           xarxa_local_cidrs="192.168.42.0/24,10.9.0.0/24,127.0.0.1/32,::1/128",
                           acces_remot_admin_only=True)


@pytest.mark.parametrize("peer,xff,enabled,trusted,expected", [
    ("203.0.113.8", None, False, "", "203.0.113.8"),
    ("192.168.42.50", None, False, "", "192.168.42.50"),
    ("testclient", "192.168.42.50", True, "127.0.0.1/32", None),
    ("172.30.0.2", "192.168.42.50", False, "", None),
    ("172.30.0.2", "192.168.42.50", True, "", None),
    ("172.30.0.2", "192.168.42.50", True, "172.30.0.2/32,invalid", None),
    ("203.0.113.8", "192.168.42.50", True, "172.30.0.2/32", None),
    ("172.30.0.20", "192.168.42.50", True, "172.30.0.2/32", None),
    ("172.30.0.2", None, True, "172.30.0.2/32", None),
    ("172.30.0.2", "", True, "172.30.0.2/32", None),
    ("172.30.0.2", "192.168.42.50", True, "172.30.0.2/32", "192.168.42.50"),
    ("172.30.0.2", "192.168.42.50, 203.0.113.8", True, "172.30.0.2/32", "203.0.113.8"),
    ("172.30.0.2", "192.168.42.50, 203.0.113.8,172.30.0.3", True, "172.30.0.2/32,172.30.0.3/32", "203.0.113.8"),
    ("172.30.0.2", "10.9.0.50,172.30.0.3", True, "172.30.0.2/32,172.30.0.3/32", "10.9.0.50"),
    ("172.30.0.2", "172.30.0.3", True, "172.30.0.2/32,172.30.0.3/32", None),
    ("172.30.0.2", "192.168.42.50,,203.0.113.8", True, "172.30.0.2/32", None),
    ("172.30.0.2", "192.168.42.50,invalid", True, "172.30.0.2/32", None),
    ("172.30.0.2", "192.168.42.50:1234", True, "172.30.0.2/32", None),
    ("2001:db8::2", "2001:db8::7", True, "2001:db8::2/128", "2001:db8::7"),
    ("172.30.0.2", "::ffff:192.168.42.50", True, "172.30.0.2/32", "192.168.42.50"),
    ("172.30.0.2", "1" * 4097, True, "172.30.0.2/32", None),
])
def test_ip_de_proxy(peer, xff, enabled, trusted, expected):
    assert ip_de_peticio(_request(peer, xff), _settings(enabled, trusted)) == expected


def test_docent_no_pot_falsejar_lan_amb_prefix_xff():
    settings = _settings()
    request = _request("172.30.0.2", "192.168.42.50,203.0.113.8,172.30.0.3")
    assert acces_es_remot(request, settings)
    with pytest.raises(HTTPException) as exc:
        comprova_acces_remot(request, SimpleNamespace(rol=Rol.DOCENT), settings)
    assert exc.value.status_code == 403
    comprova_acces_remot(request, SimpleNamespace(rol=Rol.DIRECCIO), settings)


def test_lan_i_vpn_verificades_permeten_docent():
    for ip in ("192.168.42.50", "10.9.0.50"):
        request = _request("172.30.0.2", f"{ip},172.30.0.3")
        assert not acces_es_remot(request, _settings())
        comprova_acces_remot(request, SimpleNamespace(rol=Rol.DOCENT), _settings())


def test_proxy_sense_confianca_no_es_lan_encara_que_peer_sigui_privat():
    request = _request("172.30.0.2", "192.168.42.50")
    settings = _settings(trusted="")
    settings.xarxa_local_cidrs = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    assert acces_es_remot(request, settings)
    settings.proxy_de_confianca = False
    assert acces_es_remot(request, settings)


def test_absencia_de_request_no_concede_lan():
    assert ip_de_peticio(None, _settings()) is None
    assert acces_es_remot(None, _settings())


def test_intermediari_privat_no_declarat_no_es_lan_per_defecte():
    from app.core.config import Settings
    settings = _settings(trusted="172.30.0.2/32")
    settings.xarxa_local_cidrs = Settings.model_fields["xarxa_local_cidrs"].default
    request = _request("172.30.0.2", "192.168.42.50,203.0.113.8,172.30.0.3")
    assert acces_es_remot(request, settings)
    with pytest.raises(HTTPException) as exc:
        comprova_acces_remot(request, SimpleNamespace(rol=Rol.DOCENT), settings)
    assert exc.value.status_code == 403


def test_xff_duplicat_no_defineix_la_identitat():
    request = Request({"type": "http", "client": ("172.30.0.2", 12345),
                       "headers": [(b"x-forwarded-for", b"192.168.42.50"),
                                   (b"x-forwarded-for", b"203.0.113.8")]})
    assert ip_de_peticio(request, _settings()) is None


def test_uvicorn_conserva_el_peer_real_amb_arrencada_documentada():
    """Servidor efímer loopback: XFF no pot reescriure el peer abans del guardià."""
    import json
    import socket
    import threading
    import time
    from pathlib import Path
    import httpx
    import uvicorn

    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(encoding="utf-8")
    cmd = json.loads(next(line[4:] for line in dockerfile.splitlines() if line.startswith("CMD ")))
    assert "--no-proxy-headers" in cmd

    async def app(scope, receive, send):
        request = Request(scope)
        result = {"peer": request.client.host,
                  "client": ip_de_peticio(request, _settings(trusted="127.0.0.1/32"))}
        body = json.dumps(result).encode()
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    config = uvicorn.Config(app, proxy_headers="--no-proxy-headers" not in cmd,
                            lifespan="off", log_level="critical", access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        response = httpx.get(f"http://127.0.0.1:{port}",
                             headers={"X-Forwarded-For": "192.168.42.50,203.0.113.8"},
                             trust_env=False, timeout=5)
        assert response.json() == {"peer": "127.0.0.1", "client": "203.0.113.8"}
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
