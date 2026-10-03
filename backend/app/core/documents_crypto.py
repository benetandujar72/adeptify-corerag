"""Originals: clau de domini, sobre versionat i AAD tenant+document+propòsit."""
from __future__ import annotations

import base64
import json

from app.core.config import get_settings
from app.core.crypto_envelope import open_envelope, seal

FORMAT = "aesgcm-v1"
PURPOSE = "document-original"


class OriginalNoDisponible(RuntimeError):
    """No es pot conservar/servir un original sense la protecció requerida."""


def _decode(raw: str) -> bytes:
    try:
        key = base64.b64decode(raw, validate=True)
    except (ValueError, TypeError) as exc:
        raise OriginalNoDisponible("Clau d'originals no vàlida.") from exc
    if len(key) != 32:
        raise OriginalNoDisponible("La clau d'originals ha de tenir 32 bytes.")
    return key


def keyring() -> tuple[str, dict[str, bytes]]:
    settings = get_settings()
    active = settings.documents_data_key_id
    try:
        registry = json.loads(settings.documents_data_keys or "{}")
        if not isinstance(registry, dict):
            raise ValueError
        keys = {kid: _decode(raw) for kid, raw in registry.items()
                if isinstance(kid, str) and isinstance(raw, str)}
        if len(keys) != len(registry):
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise OriginalNoDisponible("Registre de claus d'originals no vàlid.") from exc
    if settings.documents_data_key:
        key = _decode(settings.documents_data_key)
        if active in keys and keys[active] != key:
            raise OriginalNoDisponible("Identificador de clau d'originals ambigu.")
        keys[active] = key
    return active, keys


def protect(data: bytes, tenant: str, doc_id: str, *, required: bool) -> tuple[bytes, str]:
    active, keys = keyring()
    key = keys.get(active)
    if key is None:
        if required:
            raise OriginalNoDisponible("El xifratge d'originals sensibles no està configurat.")
        return bytes(data), "plain"
    try:
        return seal(data, key=key, key_id=active, tenant=tenant, record_id=doc_id, purpose=PURPOSE), FORMAT
    except Exception as exc:
        raise OriginalNoDisponible("No es pot protegir l'original del document.") from exc


def reveal(original, tenant: str, doc_id: str, *, sensitive: bool = False, migration: bool = False) -> bytes:
    if original.institucio_id != tenant or original.doc_id != doc_id:
        raise OriginalNoDisponible("El context de l'original no coincideix.")
    storage_format = original.contingut_format or "plain"
    if storage_format == "plain":
        settings = get_settings()
        if sensitive and settings.es_prod and not migration and not settings.documents_allow_legacy_sensitive:
            raise OriginalNoDisponible("Original sensible pendent de migració de xifratge.")
        return bytes(original.contingut)
    if storage_format != FORMAT:
        raise OriginalNoDisponible("Format d'original no admès.")
    try:
        _, keys = keyring()
        return open_envelope(original.contingut, keys=keys, tenant=tenant, record_id=doc_id, purpose=PURPOSE)
    except Exception as exc:
        raise OriginalNoDisponible("No es pot verificar o desxifrar l'original.") from exc
