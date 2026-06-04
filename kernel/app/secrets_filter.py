"""K8.3 — Filtre de secrets ABANS d'injectar memòria/RAG al context del model (INV-5).

Detecta i REDACTA secrets en qualsevol text que vagi al context. Backend principal:
regex d'alta precisió (determinista). Si `detect-secrets` (stack aprovat) està
instal·lat, s'usa com a escàner addicional. Cap valor de secret es registra: només
el TIPUS i el recompte (per a auditoria).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

_log = logging.getLogger("adeptify.kernel.secrets")

REDACTION = "[SECRET_REDACTAT]"

# (tipus, patró, grup_a_redactar). grup 0 = tota la coincidència.
_PATTERNS: tuple[tuple[str, re.Pattern, int], ...] = (
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), 0),
    ("aws_akia", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), 0),
    ("google_api", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), 0),
    ("slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), 0),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"), 0),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY(?: BLOCK)?-----"), 0),
    ("assignacio", re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password|passwd|pwd|contrasenya|client[_-]?secret)\b\s*[:=]\s*['\"]?([A-Za-z0-9_\-/+\.]{12,})"), 2),
)


@dataclass(frozen=True)
class SecretFinding:
    tipus: str
    inici: int
    fi: int


def scan_secrets(text: str) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    for tipus, rx, grup in _PATTERNS:
        for m in rx.finditer(text or ""):
            findings.append(SecretFinding(tipus, m.start(grup), m.end(grup)))
    # Backend addicional opcional (no bloca si no hi és). NOMÉS plugins d'ALTA
    # PRECISIÓ: excloem entropia/keyword (massa soroll en prosa → falsos positius
    # que sobre-redactarien el RAG). Així es respecta el spec (detect-secrets) sense
    # degradar el context.
    try:  # pragma: no cover - depèn de la instal·lació
        from detect_secrets.core import scan as _ds_scan  # type: ignore
        from detect_secrets.settings import transient_settings  # type: ignore

        plugins = [
            {"name": "AWSKeyDetector"}, {"name": "PrivateKeyDetector"},
            {"name": "JwtTokenDetector"}, {"name": "GitHubTokenDetector"},
            {"name": "StripeDetector"}, {"name": "SlackDetector"},
            {"name": "AzureStorageKeyDetector"}, {"name": "GitLabTokenDetector"},
        ]
        with transient_settings({"plugins_used": plugins}):
            for line in (text or "").splitlines():
                for s in _ds_scan.scan_line(line):
                    findings.append(SecretFinding(f"detect-secrets:{s.type}", -1, -1))
    except Exception:
        pass
    return findings


def redact_secrets(text: str) -> tuple[str, list[SecretFinding]]:
    """Retorna (text_redactat, findings). Registra tipus+recompte (mai el valor)."""
    if not text:
        return text, []
    findings: list[SecretFinding] = []
    out = text
    for tipus, rx, grup in _PATTERNS:
        def _sub(m: re.Match, _t=tipus, _g=grup) -> str:
            findings.append(SecretFinding(_t, m.start(_g), m.end(_g)))
            if _g == 0:
                return REDACTION
            return m.group(0)[: m.start(_g) - m.start(0)] + REDACTION
        out = rx.sub(_sub, out)
    if findings:
        tipus_count: dict[str, int] = {}
        for f in findings:
            tipus_count[f.tipus] = tipus_count.get(f.tipus, 0) + 1
        _log.warning("secrets redactats abans del context: %s", tipus_count)
    return out, findings


def context_es_net(text: str) -> bool:
    """True si el text NO conté cap secret detectable (per a asserts)."""
    return not scan_secrets(text)
