"""K5.1/K5.2 — Router de models LOCALS (Ollama/vLLM, OpenAI-compat).

INV-3 (capa d'aplicació): rebutja QUALSEVOL endpoint fora de la LAN aprovada a
l'arrencada (p. ex. api.openai.com). La regla de xarxa real (firewall/egress) és
una fase posterior; aquí garantim que el kernel no es configura mai cap a un host
extern i que `external_calls` queda a 0.
K5.2: allowlist de models + verificació del hash SHA-256 del manifest.
"""

from __future__ import annotations

import hashlib
import ipaddress
import pathlib
from urllib.parse import urlparse

import strictyaml

from .config import KernelSettings, get_settings
from .errors import AllowlistError, ExternalEndpointError

# Mètrica observable: nombre de crides a endpoints EXTERNS realitzades. Per disseny
# ROMAN 0: cap crida surt mai de la LAN (es rebutja a la configuració). A part,
# comptem els INTENTS bloquejats (mètrica de seguretat) sense contaminar external_calls.
_external_calls = 0
_blocked_external_attempts = 0


def external_calls() -> int:
    return _external_calls


def blocked_external_attempts() -> int:
    return _blocked_external_attempts


def _registra_intent_bloquejat() -> None:
    global _blocked_external_attempts
    _blocked_external_attempts += 1


def _es_lan(host: str, settings: KernelSettings) -> bool:
    h = (host or "").lower()
    if h in settings.lan_hosts_list:
        return True
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return False  # hostname desconegut i no a la llista → NO és LAN
    for cidr in settings.lan_cidrs_list:
        try:
            if ip in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def assert_local_endpoint(base_url: str, settings: KernelSettings | None = None) -> str:
    """Llança ExternalEndpointError si `base_url` no és de la LAN aprovada (K5.1/INV-3)."""
    settings = settings or get_settings()
    host = urlparse(base_url).hostname
    if not host or not _es_lan(host, settings):
        _registra_intent_bloquejat()
        raise ExternalEndpointError(
            f"Endpoint de model FORA de la LAN aprovada: {base_url!r} (host={host}). "
            "El kernel només admet inferència local (INV-3)."
        )
    return host


def load_models_manifest(path: str, *, expected_sha256: str | None = None) -> dict:
    """Carrega el manifest de models verificant-ne el hash SHA-256 (K5.2)."""
    raw = pathlib.Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise AllowlistError(
            f"Hash del manifest de models no coincideix (esperat {expected_sha256[:12]}…, és {digest[:12]}…)"
        )
    doc = strictyaml.load(raw.decode("utf-8")).data
    models = [m["name"] for m in (doc.get("models", []) or [])]
    return {"sha256": digest, "models": models}


class ModelRouter:
    """Adaptador a un endpoint OpenAI-compat LOCAL amb allowlist de models."""

    def __init__(self, *, base_url: str, allowed_models, settings: KernelSettings | None = None) -> None:
        self._settings = settings or get_settings()
        # K5.1/INV-3: validació a l'arrencada; si és extern, NO arrenca.
        self.host = assert_local_endpoint(base_url, self._settings)
        self.base_url = base_url
        self._allowed = set(allowed_models)

    def ensure_model(self, name: str) -> str:
        if name not in self._allowed:
            raise AllowlistError(f"Model «{name}» fora de l'allowlist de models (K5.2)")
        return name

    @property
    def allowed_models(self) -> set[str]:
        return set(self._allowed)
