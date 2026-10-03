"""Real browser-cookie and service-Bearer regression tests; synthetic identities."""
import pytest

AUTENTICACIO_REAL = True


@pytest.fixture()
def browser(client, db, monkeypatch):
    from app.core.config import get_settings
    from app.core import users
    settings = get_settings()
    monkeypatch.setattr(settings, "browser_session_allowed_origins", "https://testserver")
    monkeypatch.setattr(settings, "browser_session_allow_http_dev", False)
    monkeypatch.setattr(settings, "acces_remot_admin_only", False)
    users.crea_usuari(db, "cookie_doc", "test-pass-only", "docent")
    db.commit()
    client.base_url = "https://testserver"
    return client


def _login(browser, origin="https://testserver"):
    return browser.post("/api/auth/login", json={"usuari": "cookie_doc", "contrasenya": "test-pass-only"},
                        headers={"X-Adeptify-Session": "cookie", "Origin": origin})


def test_browser_login_cookie_httponly_secure_samesite_no_jwt_json(browser):
    response = _login(browser)
    assert response.status_code == 200
    assert response.json()["token"] == ""
    headers = response.headers.get_list("set-cookie")
    session = next(h for h in headers if h.startswith("__Host-adeptify_session="))
    assert "HttpOnly" in session and "Secure" in session and "SameSite=strict" in session
    assert "Path=/" in session and "Domain=" not in session
    assert response.headers["cache-control"] == "no-store"
    assert browser.get("/api/auth/me").json()["usuari"] == "cookie_doc"


def test_old_browser_login_cannot_receive_a_json_jwt(browser):
    response = browser.post("/api/auth/login", json={"usuari": "cookie_doc", "contrasenya": "test-pass-only"},
                            headers={"Origin": "https://testserver"})
    assert response.status_code == 200
    assert response.json()["token"] == ""
    assert response.headers.get_list("set-cookie")


@pytest.mark.parametrize("origin", ["https://evil.invalid", "https://testserver.evil.invalid",
                                   "http://testserver", "null", ""])
def test_browser_login_origin_fail_closed(browser, origin):
    response = _login(browser, origin)
    assert response.status_code == 403
    assert not response.headers.get_list("set-cookie")


@pytest.mark.parametrize("origin,csrf", [("https://testserver", ""), ("https://testserver", "forged"),
                                        ("https://evil.invalid", "valid"), ("", "valid")])
def test_cookie_csrf_rejected(browser, origin, csrf):
    assert _login(browser).status_code == 200
    if csrf == "valid":
        csrf = browser.cookies.get("__Host-adeptify_csrf")
    response = browser.patch("/api/auth/idioma", json={"idioma": "es"},
                             headers={"Origin": origin, "X-Adeptify-CSRF": csrf})
    assert response.status_code == 403


def test_cookie_csrf_valid_and_logout_revokes(browser):
    assert _login(browser).status_code == 200
    token = browser.cookies.get("__Host-adeptify_session")
    headers = {"Origin": "https://testserver",
               "X-Adeptify-CSRF": browser.cookies.get("__Host-adeptify_csrf")}
    assert browser.patch("/api/auth/idioma", json={"idioma": "es"}, headers=headers).status_code == 200
    assert browser.post("/api/auth/logout", headers=headers).status_code == 200
    assert browser.get("/api/auth/me").status_code == 401
    assert browser.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_role_and_revocation_revalidated_for_cookies(browser, db):
    from app.core import users
    assert _login(browser).status_code == 200
    user = users.obte_usuari(db, "cookie_doc")
    user.rol = "familia"
    db.commit()
    assert browser.get("/api/auth/me").json()["rol"] == "familia"
    user.token_version = int(user.token_version or 0) + 1
    db.commit()
    assert browser.get("/api/auth/me").status_code == 401


def test_explicit_service_bearer_remains_usable_without_cookie_csrf(browser):
    response = browser.post("/api/auth/login", json={"usuari": "cookie_doc", "contrasenya": "test-pass-only"})
    assert response.status_code == 200
    token = response.json()["token"]
    assert token and not response.headers.get_list("set-cookie")
    assert not browser.cookies
    response = browser.patch("/api/auth/idioma", json={"idioma": "es"},
                             headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_csrf_is_bound_to_entire_session_jwt(browser):
    from app.core.browser_session import csrf_per_token
    from app.core.config import get_settings
    assert _login(browser).status_code == 200
    forged_for_another_token = csrf_per_token("another-synthetic-token", get_settings())
    response = browser.patch("/api/auth/idioma", json={"idioma": "es"},
                             headers={"Origin": "https://testserver",
                                      "X-Adeptify-CSRF": forged_for_another_token})
    assert response.status_code == 403


def test_duplicate_csrf_headers_rejected(browser):
    assert _login(browser).status_code == 200
    csrf = browser.cookies.get("__Host-adeptify_csrf")
    response = browser.patch("/api/auth/idioma", json={"idioma": "es"},
                             headers=[("Origin", "https://testserver"),
                                      ("X-Adeptify-CSRF", csrf), ("X-Adeptify-CSRF", csrf)])
    assert response.status_code == 403


def test_http_dev_exception_requires_explicit_flag_and_loopback(monkeypatch):
    from types import SimpleNamespace
    from fastapi import Request
    from app.core.browser_session import protegeix_entrada
    settings = SimpleNamespace(entorn="prod-onprem", browser_session_allow_http_dev=True,
                               browser_session_allowed_origins="http://localhost:5173")
    request = Request({"type": "http", "headers": [(b"x-adeptify-session", b"cookie"),
                                                  (b"origin", b"http://localhost:5173")]})
    with pytest.raises(Exception) as exc:
        protegeix_entrada(request, settings)
    assert exc.value.status_code == 403
    settings.entorn = "dev"
    protegeix_entrada(request, settings)
    settings.browser_session_allow_http_dev = False
    with pytest.raises(Exception):
        protegeix_entrada(request, settings)

