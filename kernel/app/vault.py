"""INV-5 — Vault de procés separat per als secrets.

Els secrets (clau dels capability tokens, passphrase GPG, credencials de BD) viuen
AQUÍ i MAI s'inclouen al context que s'envia al model. El vault NO és serialitzable
ni es passa al prompt builder; només el kernel d'eines/auth hi accedeix via `get()`.

`assert_no_secrets()` permet als tests verificar que cap valor secret apareix en un
objecte de context destinat al model.
"""

from __future__ import annotations

import json
import os
from typing import Any


class Vault:
    """Magatzem de secrets en memòria de procés. No es loggeja ni es serialitza."""

    __slots__ = ("_secrets",)

    def __init__(self, secrets: dict[str, str] | None = None) -> None:
        object.__setattr__(self, "_secrets", dict(secrets or {}))

    @classmethod
    def from_env(cls) -> "Vault":
        """Carrega els secrets coneguts des de l'entorn (no entren mai al context)."""
        noms = (
            "KERNEL_CAPABILITY_SECRET",
            "KERNEL_GPG_PASSPHRASE",
            "KERNEL_DB_PASSWORD",
        )
        return cls({n: os.environ[n] for n in noms if os.environ.get(n)})

    def get(self, nom: str, default: str | None = None) -> str | None:
        return self._secrets.get(nom, default)

    def require(self, nom: str) -> str:
        val = self._secrets.get(nom)
        if not val:
            raise KeyError(f"Secret «{nom}» absent del vault")
        return val

    def set(self, nom: str, valor: str) -> None:
        self._secrets[nom] = valor

    @property
    def noms(self) -> list[str]:
        return list(self._secrets)

    # ── Anti-fuita ──
    def __repr__(self) -> str:  # mai exposem valors
        return f"<Vault noms={list(self._secrets)} (valors ocults)>"

    def __str__(self) -> str:
        return self.__repr__()


def assert_no_secrets(context: Any, vault: Vault) -> None:
    """Llança AssertionError si algun valor secret del vault apareix dins `context`.

    `context` és qualsevol estructura (dict/list/str) destinada al model. Serialitzem
    a JSON i comprovem que cap valor secret hi és literal.
    """
    valors = [v for v in (vault.get(n) for n in vault.noms) if v]
    if not valors:
        return
    blob = json.dumps(context, default=str, ensure_ascii=False)
    for v in valors:
        if v and v in blob:
            raise AssertionError("FUITA DE SECRET: un valor del vault apareix al context del model")
