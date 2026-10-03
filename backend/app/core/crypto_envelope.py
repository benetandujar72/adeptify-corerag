"""Sobre AES-GCM v1, amb versió/clau i context autenticats (mai claus al blob)."""
from __future__ import annotations

import json
import os
import struct

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"ADPT-AEAD\x00\x01"


def _aad(header: bytes, tenant: str, record_id: str, purpose: str) -> bytes:
    if not all(isinstance(v, str) and v for v in (tenant, record_id, purpose)):
        raise ValueError("El context de xifratge ha de ser explícit.")
    return MAGIC + header + json.dumps(
        [tenant, record_id, purpose], ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def seal(data: bytes, *, key: bytes, key_id: str, tenant: str, record_id: str, purpose: str) -> bytes:
    if len(key) != 32 or not isinstance(key_id, str) or not key_id or len(key_id) > 128:
        raise ValueError("Clau o identificador de clau no vàlid.")
    header = json.dumps({"v": 1, "kid": key_id}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, bytes(data), _aad(header, tenant, record_id, purpose))
    return MAGIC + struct.pack("!H", len(header)) + header + nonce + ciphertext


def open_envelope(blob: bytes, *, keys: dict[str, bytes], tenant: str, record_id: str, purpose: str) -> bytes:
    blob = bytes(blob)
    offset = len(MAGIC)
    if not blob.startswith(MAGIC) or len(blob) < offset + 2:
        raise ValueError("Sobre de xifratge no vàlid.")
    size = struct.unpack("!H", blob[offset:offset + 2])[0]
    offset += 2
    if not 1 <= size <= 1024 or len(blob) < offset + size + 28:
        raise ValueError("Sobre de xifratge truncat.")
    header = blob[offset:offset + size]
    metadata = json.loads(header)
    if not isinstance(metadata, dict) or metadata.get("v") != 1 or not isinstance(metadata.get("kid"), str):
        raise ValueError("Versió de xifratge no admesa.")
    key = keys.get(metadata["kid"])
    if key is None or len(key) != 32:
        raise ValueError("Clau de desxifratge no disponible.")
    offset += size
    return AESGCM(key).decrypt(blob[offset:offset + 12], blob[offset + 12:],
                               _aad(header, tenant, record_id, purpose))
