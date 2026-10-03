"""Browser sessions: host-only HttpOnly cookies and JWT-bound CSRF.

Bearer authentication remains available for server-to-server callers. Browser
login explicitly requests cookies and never receives its JWT in the JSON body.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import time
from urllib.parse import urlsplit

import jwt
from fastapi import HTTPException, Request, Response

SESSION_COOKIE = "__Host-adeptify_session"
CSRF_COOKIE = "__Host-adeptify_csrf"
BROWSER_HEADER = "x-adeptify-session"
CSRF_HEADER = "x-adeptify-csrf"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def es_navegador(request: Request) -> bool:
    # Old cached SPA clients must not receive a JWT in JSON either.
    return (request.headers.get(BROWSER_HEADER) == "cookie" or
            "origin" in request.headers or "sec-fetch-mode" in request.headers)


def _secure(settings) -> bool:
    return not (settings.entorn == "dev" and settings.browser_session_allow_http_dev)


def _origen(request: Request, settings) -> None:
    origin = request.headers.get("origin", "")
    allowed = {s.strip().rstrip("/") for s in settings.browser_session_allowed_origins.split(",") if s.strip()}
    try:
        parsed = urlsplit(origin)
        valid = (origin in allowed and parsed.scheme in {"https", "http"} and parsed.hostname
                 and not parsed.username and not parsed.password and not parsed.query
                 and not parsed.fragment and parsed.path in {"", "/"})
        if parsed.scheme != "https":
            try:
                loopback = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname or "").is_loopback
            except ValueError:
                loopback = False
            valid = valid and not _secure(settings) and loopback
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(status_code=403, detail="Origen de sessió no autoritzat.")


def protegeix_entrada(request: Request, settings) -> None:
    # An unmarked service login never creates a browser cookie.
    if es_navegador(request):
        _origen(request, settings)


def csrf_per_token(token: str, settings) -> str:
    return hmac.new(settings.jwt_secret.encode(),
                    b"adeptify-browser-csrf-v1\0" + token.encode(), hashlib.sha256).hexdigest()


def token_de_peticio(request: Request, authorization: str | None, settings) -> str:
    if authorization is not None:
        if not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Autorització invàlida.")
        token = authorization.split(" ", 1)[1].strip()
        if not token:
            raise HTTPException(status_code=401, detail="Autorització invàlida.")
        return token  # Explicit credentials are not ambient browser credentials.
    cookie_name = SESSION_COOKIE if _secure(settings) else "adeptify_session_dev"
    token = request.cookies.get(cookie_name, "")
    if not token:
        raise HTTPException(status_code=401, detail="Falta la sessió.")
    if request.method not in SAFE_METHODS:
        _origen(request, settings)
        supplied = request.headers.get(CSRF_HEADER, "")
        if (len(request.headers.getlist(CSRF_HEADER)) != 1 or
                not hmac.compare_digest(supplied, csrf_per_token(token, settings))):
            raise HTTPException(status_code=403, detail="Protecció CSRF: petició rebutjada.")
    return token


def resposta_sessio(token: str, response: Response, request: Request, settings) -> str:
    if not es_navegador(request):
        return token
    _origen(request, settings)
    payload = jwt.decode(token, options={"verify_signature": False})
    ttl = max(0, int(payload["exp"]) - int(time.time()))
    secure = _secure(settings)
    session_name = SESSION_COOKIE if secure else "adeptify_session_dev"
    csrf_name = CSRF_COOKIE if secure else "adeptify_csrf_dev"
    response.set_cookie(session_name, token, max_age=ttl, path="/", httponly=True,
                        secure=secure, samesite="strict")
    response.set_cookie(csrf_name, csrf_per_token(token, settings), max_age=ttl, path="/",
                        httponly=False, secure=secure, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return ""


def esborra_sessio(response: Response, settings) -> None:
    secure = _secure(settings)
    response.delete_cookie(SESSION_COOKIE if secure else "adeptify_session_dev", path="/", secure=secure,
                           httponly=True, samesite="strict")
    response.delete_cookie(CSRF_COOKIE if secure else "adeptify_csrf_dev", path="/", secure=secure, samesite="strict")
    response.headers["Cache-Control"] = "no-store"

