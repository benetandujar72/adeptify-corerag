"""K3.1 — Allowlist firmada GPG: càrrega, verificació i rebuig de manipulació."""

from __future__ import annotations

import pathlib

import pytest

from app.allowlist import load_signed_allowlist, verify_gpg_signature
from app.errors import AllowlistError

AL = "/app/allowlist"


def test_carrega_allowlist_signada_ok():
    al = load_signed_allowlist(
        data_path=f"{AL}/tools.yaml", sig_path=f"{AL}/tools.yaml.sig", pubkey_path=f"{AL}/pubkey.asc",
    )
    assert {"echo.info", "fs.read_synthetic", "kv.put_local"} <= al.ids
    assert al.fingerprint  # signatura verificada
    assert al.require("echo.info").risk.etiqueta == "info"


def test_allowlist_manipulada_es_rebutjada(tmp_path):
    # Un fitxer amb contingut ALTERAT contra la signatura real → signatura invàlida.
    fals = tmp_path / "tools.yaml"
    fals.write_text(
        pathlib.Path(f"{AL}/tools.yaml").read_text(encoding="utf-8") + "\n  - id: evil.injected\n    risk: irreversible\n",
        encoding="utf-8",
    )
    with pytest.raises(AllowlistError):
        verify_gpg_signature(
            data_path=str(fals), sig_path=f"{AL}/tools.yaml.sig", pubkey_path=f"{AL}/pubkey.asc",
        )


def test_eina_fora_allowlist_no_es_pot_requerir():
    al = load_signed_allowlist(
        data_path=f"{AL}/tools.yaml", sig_path=f"{AL}/tools.yaml.sig", pubkey_path=f"{AL}/pubkey.asc",
    )
    assert "evil.injected" not in al
    with pytest.raises(AllowlistError):
        al.require("evil.injected")


# ── F4.0a · Pinning de fingerprint GPG (gate G-D) ────────────────────────────
def _fp_real() -> str:
    return verify_gpg_signature(
        data_path=f"{AL}/tools.yaml", sig_path=f"{AL}/tools.yaml.sig", pubkey_path=f"{AL}/pubkey.asc",
    )


def test_pinning_fingerprint_correcte_accepta():
    fp = _fp_real()
    assert fp
    # Amb el fingerprint correcte fixat, la verificació passa i el retorna.
    assert verify_gpg_signature(
        data_path=f"{AL}/tools.yaml", sig_path=f"{AL}/tools.yaml.sig", pubkey_path=f"{AL}/pubkey.asc",
        expected_fingerprint=fp,
    ) == fp


def test_pinning_fingerprint_incorrecte_rebutjat():
    """Signatura VÀLIDA però fingerprint NO confiat → rebuig (tanca G-D)."""
    with pytest.raises(AllowlistError):
        verify_gpg_signature(
            data_path=f"{AL}/tools.yaml", sig_path=f"{AL}/tools.yaml.sig", pubkey_path=f"{AL}/pubkey.asc",
            expected_fingerprint="0000000000000000000000000000000000000000",
        )


def test_pinning_via_entorn(monkeypatch):
    # Fingerprint de confiança erroni via entorn → load_signed_allowlist el rebutja.
    monkeypatch.setenv("KERNEL_TRUSTED_GPG_FINGERPRINT", "DEADBEEF" * 5)
    with pytest.raises(AllowlistError):
        load_signed_allowlist(
            data_path=f"{AL}/tools.yaml", sig_path=f"{AL}/tools.yaml.sig", pubkey_path=f"{AL}/pubkey.asc",
        )
    # Amb el fingerprint correcte via entorn → carrega OK.
    monkeypatch.setenv("KERNEL_TRUSTED_GPG_FINGERPRINT", _fp_real())
    al = load_signed_allowlist(
        data_path=f"{AL}/tools.yaml", sig_path=f"{AL}/tools.yaml.sig", pubkey_path=f"{AL}/pubkey.asc",
    )
    assert al.fingerprint
