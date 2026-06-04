"""K2.2 — Capability tokens JWT de vida curta.

Després que la política permeti una acció, el kernel encunya un capability token
(TTL 60–300s) amb claims tool_id, session_id, tenant_id, risk_level. L'eina el
verifica ABANS d'executar-se: rebutja caducats, signatura dolenta, o tool_id/
session_id que no coincideixen. El secret de signatura viu al vault (INV-5).
"""

from __future__ import annotations

import datetime as dt
import secrets
from dataclasses import dataclass

import jwt

from .errors import CapabilityError


@dataclass(frozen=True)
class CapabilityClaims:
    tool_id: str
    session_id: str
    tenant_id: str
    risk_level: int
    jti: str
    iat: int
    exp: int


class CapabilityIssuer:
    def __init__(
        self, secret: str, *, ttl_s: int = 120, ttl_min_s: int = 60, ttl_max_s: int = 300,
        issuer: str = "adeptify-kernel", audience: str = "adeptify-tools", algorithm: str = "HS256",
    ) -> None:
        if not secret or len(secret) < 16:
            raise CapabilityError("El secret de capability ha de tenir >= 16 caràcters")
        self._secret = secret
        self._ttl = max(int(ttl_min_s), min(int(ttl_s), int(ttl_max_s)))  # TTL acotat 60..300
        self._iss = issuer
        self._aud = audience
        self._alg = algorithm

    @property
    def ttl_s(self) -> int:
        return self._ttl

    def mint(
        self, *, tool_id: str, session_id: str, tenant_id: str, risk_level: int,
        _now: dt.datetime | None = None,
    ) -> str:
        now = _now or dt.datetime.now(dt.timezone.utc)
        payload = {
            "tool_id": tool_id,
            "session_id": session_id,
            "tenant_id": tenant_id,
            "risk_level": int(risk_level),
            "jti": secrets.token_hex(16),
            "iss": self._iss,
            "aud": self._aud,
            "iat": int(now.timestamp()),
            "exp": int((now + dt.timedelta(seconds=self._ttl)).timestamp()),
        }
        return jwt.encode(payload, self._secret, algorithm=self._alg)

    def verify(self, token: str, *, expected_tool_id: str, expected_session_id: str) -> CapabilityClaims:
        try:
            data = jwt.decode(
                token, self._secret, algorithms=[self._alg],
                audience=self._aud, issuer=self._iss,
            )
        except jwt.ExpiredSignatureError as exc:
            raise CapabilityError("Capability token caducat") from exc
        except jwt.InvalidTokenError as exc:
            raise CapabilityError(f"Capability token invàlid: {exc}") from exc

        if data.get("tool_id") != expected_tool_id:
            raise CapabilityError(
                f"tool_id del capability no coincideix (esperat {expected_tool_id!r})"
            )
        if data.get("session_id") != expected_session_id:
            raise CapabilityError("session_id del capability no coincideix")
        return CapabilityClaims(
            tool_id=data["tool_id"], session_id=data["session_id"], tenant_id=data["tenant_id"],
            risk_level=int(data["risk_level"]), jti=data["jti"], iat=data["iat"], exp=data["exp"],
        )
