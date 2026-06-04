"""App FastAPI del kernel — superfície mínima (health + status). Sense /docs exposat."""

from __future__ import annotations

from fastapi import FastAPI

from . import __version__
from .models_router import blocked_external_attempts, external_calls

# docs_url/redoc_url None: cap superfície d'API innecessària.
app = FastAPI(title="Adeptify Secure Agent Kernel", version=__version__, docs_url=None, redoc_url=None)


@app.get("/health")
def health() -> dict:
    return {"estat": "ok", "versio": __version__}


@app.get("/status")
def status() -> dict:
    return {
        "versio": __version__,
        "egress": "zero (només LAN aprovada)",
        "external_calls": external_calls(),               # ha de ser 0 (INV-3)
        "blocked_external_attempts": blocked_external_attempts(),
    }
