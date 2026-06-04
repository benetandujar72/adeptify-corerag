"""K3.1 — Allowlist estàtica d'eines firmada GPG (sense descobriment dinàmic).

L'allowlist (`tools.yaml`) es verifica contra una signatura GPG separada
(`tools.yaml.sig`) amb una clau pública de confiança (`pubkey.asc`). Si la
signatura no és vàlida o falta, es llança AllowlistError a l'arrencada (INV-4).
Cap eina es descobreix en runtime: tot ve d'aquest fitxer signat.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import gnupg
import strictyaml

from .errors import AllowlistError
from .risk import RiskLevel, parse_risk


@dataclass(frozen=True)
class AllowedTool:
    id: str
    risk: RiskLevel
    descripcio: str = ""


class SignedAllowlist:
    def __init__(self, tools: dict[str, AllowedTool], *, fingerprint: str | None = None) -> None:
        self._tools = dict(tools)
        self.fingerprint = fingerprint

    def __contains__(self, tool_id: str) -> bool:
        return tool_id in self._tools

    def get(self, tool_id: str) -> AllowedTool | None:
        return self._tools.get(tool_id)

    def require(self, tool_id: str) -> AllowedTool:
        t = self._tools.get(tool_id)
        if t is None:
            raise AllowlistError(f"Eina «{tool_id}» FORA de l'allowlist signada")
        return t

    @property
    def ids(self) -> set[str]:
        return set(self._tools)


def verify_gpg_signature(*, data_path: str, sig_path: str, pubkey_path: str,
                         gnupghome: str | None = None) -> str:
    """Verifica la signatura GPG separada. Retorna el fingerprint o llança AllowlistError."""
    gpg = gnupg.GPG(gnupghome=gnupghome) if gnupghome else gnupg.GPG()
    pub = pathlib.Path(pubkey_path).read_text(encoding="utf-8")
    imported = gpg.import_keys(pub)
    if not imported.fingerprints:
        raise AllowlistError("No s'ha pogut importar la clau pública de l'allowlist")
    with open(sig_path, "rb") as sig:
        verified = gpg.verify_file(sig, str(data_path))
    if not getattr(verified, "valid", False):
        estat = getattr(verified, "status", "desconegut")
        raise AllowlistError(f"Signatura GPG de l'allowlist INVÀLIDA (estat: {estat})")
    return verified.fingerprint


def load_signed_allowlist(*, data_path: str, sig_path: str, pubkey_path: str,
                          gnupghome: str | None = None, verify: bool = True) -> SignedAllowlist:
    """Carrega l'allowlist DESPRÉS de verificar la seva signatura GPG."""
    fingerprint = None
    if verify:
        fingerprint = verify_gpg_signature(
            data_path=data_path, sig_path=sig_path, pubkey_path=pubkey_path, gnupghome=gnupghome
        )
    raw = pathlib.Path(data_path).read_text(encoding="utf-8")
    try:
        doc = strictyaml.load(raw).data
    except Exception as exc:  # noqa: BLE001 - YAML invàlid és error d'allowlist
        raise AllowlistError(f"Allowlist YAML invàlid: {exc}") from exc

    tools: dict[str, AllowedTool] = {}
    for entry in doc.get("tools", []) or []:
        tid = entry["id"]
        tools[tid] = AllowedTool(id=tid, risk=parse_risk(entry["risk"]),
                                 descripcio=entry.get("descripcio", ""))
    if not tools:
        raise AllowlistError("Allowlist buida o sense secció 'tools'")
    return SignedAllowlist(tools, fingerprint=fingerprint)
