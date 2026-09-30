"""Oferiment del codi font (AGPL-3.0-or-later, article 13).

L'article 13 de l'AGPL obliga qui ofereix el programa MODIFICAT a usuaris que hi interactuen per la xarxa a
oferir-los el codi font corresponent, de manera visible i sense cost. El nucli el compleix per dues vies:
l'enllaç «Codi font (AGPL)» al peu de la interfície i aquest endpoint públic, sense autenticació, per a
qualsevol client de l'API. `codi_font_url` ha d'apuntar al repositori del codi que corre de debò: qui
desplegui un fork amb canvis l'ha de canviar pel seu.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import Settings, get_settings

router = APIRouter(prefix="/api", tags=["codi-font"])

LLICENCIA = "AGPL-3.0-or-later"


class CodiFontResponse(BaseModel):
    llicencia: str
    repositori: str
    versio: str
    commit: str | None
    text_llicencia: str


@router.get("/codi-font", response_model=CodiFontResponse)
def codi_font(settings: Settings = Depends(get_settings)) -> CodiFontResponse:
    """On és el codi font d'aquesta instància (AGPL §13). Públic: cap dada, cap autenticació."""
    repo = settings.codi_font_url.rstrip("/")
    commit = (settings.codi_font_commit or "").strip() or None
    return CodiFontResponse(
        llicencia=LLICENCIA,
        repositori=f"{repo}/tree/{commit}" if commit else repo,
        versio=settings.versio,
        commit=commit,
        text_llicencia=f"{repo}/blob/{commit or 'master'}/LICENSE",
    )
