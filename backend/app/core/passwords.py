"""Hashing de contrasenyes amb la biblioteca estàndard (sense dependències noves).

Format emmagatzemat: `pbkdf2_sha256$<iteracions>$<salt_hex>$<hash_hex>`.
Verificació en temps constant per evitar timing attacks.
"""

from __future__ import annotations

import hashlib
import hmac
import os

_ALG = "pbkdf2_sha256"
_ITERS = 240_000
_SALT_BYTES = 16


def hash_password(contrasenya: str, *, iteracions: int = _ITERS) -> str:
    """Genera el hash emmagatzemable d'una contrasenya."""
    salt = os.urandom(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", contrasenya.encode("utf-8"), salt, iteracions)
    return f"{_ALG}${iteracions}${salt.hex()}${dk.hex()}"


def verify_password(contrasenya: str, hash_emmagatzemat: str) -> bool:
    """Comprova una contrasenya contra el hash emmagatzemat (temps constant)."""
    try:
        alg, iters_s, salt_hex, hash_hex = hash_emmagatzemat.split("$")
        if alg != _ALG:
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", contrasenya.encode("utf-8"), bytes.fromhex(salt_hex), int(iters_s)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False
