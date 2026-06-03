"""TOTP (RFC 6238) amb la biblioteca estàndard — SENSE dependències noves.

Coherent amb l'enfocament de `passwords.py` (PBKDF2 sense deps). Compatible amb
Google Authenticator, Authy, FreeOTP, etc. (SHA-1, 6 dígits, període 30 s).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from urllib.parse import quote


def genera_secret() -> str:
    """Clau secreta aleatòria en base32 (sense farciment), per a l'enrolment."""
    return base64.b32encode(os.urandom(20)).decode("ascii").rstrip("=")


def _codi_per_comptador(secret_b32: str, comptador: int) -> str:
    pad = "=" * ((8 - len(secret_b32) % 8) % 8)
    clau = base64.b32decode(secret_b32.upper() + pad, casefold=True)
    missatge = struct.pack(">Q", comptador)
    h = hmac.new(clau, missatge, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    codi = (struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{codi:06d}"


def verifica(secret_b32: str, codi: str, *, finestra: int = 1, periode: int = 30) -> bool:
    """Verifica un codi TOTP, tolerant ±`finestra` períodes (desfàs de rellotge)."""
    codi = (codi or "").strip().replace(" ", "")
    if not secret_b32 or not codi.isdigit() or len(codi) != 6:
        return False
    ara = int(time.time() // periode)
    for delta in range(-finestra, finestra + 1):
        if hmac.compare_digest(_codi_per_comptador(secret_b32, ara + delta), codi):
            return True
    return False


def uri_otpauth(secret_b32: str, usuari: str, emissor: str = "Adeptify RAG") -> str:
    """URI `otpauth://` per generar el codi QR a l'app d'autenticació."""
    etiqueta = quote(f"{emissor}:{usuari}", safe="")
    return (
        f"otpauth://totp/{etiqueta}"
        f"?secret={secret_b32}&issuer={quote(emissor, safe='')}&period=30&digits=6&algorithm=SHA1"
    )
