"""Autenticació service-to-service del servei intern del nucli (/api/servei/*).

El suite (adeptify-suiterag, privat) consumeix el nucli per una API local. Aquesta
dependència verifica el secret compartit (CORE_SERVICE_TOKEN) en TEMPS CONSTANT.
NO és un usuari: acredita que la crida prové del suite de confiança (mateixa LAN).

Defensa en profunditat: si CORE_SERVICE_TOKEN no està configurat, el servei queda
DESACTIVAT (503). El nucli no delega cap inferència fins que s'hi posa un secret.
"""

from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings


def _extreu_token(authorization: str | None, x_service_token: str | None) -> str:
    """Token del client: prioritza X-Service-Token; si no, Authorization: Bearer."""
    if x_service_token:
        return x_service_token.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def verifica_servei(
    authorization: str | None = Header(default=None),
    x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
    settings: Settings = Depends(get_settings),
) -> str:
    """Dependència FastAPI: exigeix un token de servei vàlid.

    - 503 si el servei no està configurat (CORE_SERVICE_TOKEN buit).
    - 401 si el token falta o no coincideix (comparació en temps constant).
    Retorna un identificador del cridador per a l'auditoria (sense PII).
    """
    esperat = (settings.core_service_token or "").strip()
    if not esperat:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servei intern desactivat (CORE_SERVICE_TOKEN no configurat).",
        )
    rebut = _extreu_token(authorization, x_service_token)
    if not rebut or not hmac.compare_digest(rebut.encode("utf-8"), esperat.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de servei invàlid.",
        )
    return "servei:suite"
