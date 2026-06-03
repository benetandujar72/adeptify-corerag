"""Gestió d'errors uniforme segons API_CONTRACT.md.

Format: { "error": { "codi": "...", "missatge": "..." } } amb el codi HTTP
corresponent (403/404/429/500/400). Es registren handlers a l'app FastAPI.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Mapatge de codi HTTP → codi del contracte.
_HTTP_A_CODI = {
    400: "BAD_REQUEST",
    401: "FORBIDDEN",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    429: "RATE_LIMIT",
    500: "INTERNAL",
}


def _resposta_error(status_code: int, missatge: str) -> JSONResponse:
    codi = _HTTP_A_CODI.get(status_code, "INTERNAL")
    return JSONResponse(
        status_code=status_code,
        content={"error": {"codi": codi, "missatge": missatge}},
    )


def registra_handlers(app: FastAPI) -> None:
    """Registra els handlers d'error a l'aplicació."""

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        detall = exc.detail if isinstance(exc.detail, str) else "Error."
        return _resposta_error(exc.status_code, detall)

    @app.exception_handler(RequestValidationError)
    async def _validacio(request: Request, exc: RequestValidationError):
        return _resposta_error(400, "Petició invàlida o incompleta.")

    @app.exception_handler(Exception)
    async def _generic(request: Request, exc: Exception):  # pragma: no cover
        return _resposta_error(500, "Error intern del servidor.")
