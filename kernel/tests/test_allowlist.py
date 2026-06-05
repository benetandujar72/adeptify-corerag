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


def test_pinning_obligatori_en_prod(monkeypatch):
    """Red-team F4: en PRODUCCIÓ, sense fingerprint fixat, la verificació GPG es
    rebutja (fail-closed G-D); no n'hi ha prou amb una signatura vàlida."""
    from app.config import get_settings

    fp = _fp_real()  # obté el fingerprint real ABANS d'activar prod (en dev no hi ha pinning)
    monkeypatch.delenv("KERNEL_TRUSTED_GPG_FINGERPRINT", raising=False)
    monkeypatch.setenv("ENTORN", "prod")
    get_settings.cache_clear()
    try:
        with pytest.raises(AllowlistError):
            verify_gpg_signature(
                data_path=f"{AL}/tools.yaml", sig_path=f"{AL}/tools.yaml.sig",
                pubkey_path=f"{AL}/pubkey.asc",
            )
        # Amb el fingerprint correcte fixat, en prod, SÍ que verifica.
        monkeypatch.setenv("KERNEL_TRUSTED_GPG_FINGERPRINT", fp)
        get_settings.cache_clear()
        assert verify_gpg_signature(
            data_path=f"{AL}/tools.yaml", sig_path=f"{AL}/tools.yaml.sig",
            pubkey_path=f"{AL}/pubkey.asc",
        )
    finally:
        get_settings.cache_clear()


def test_pinning_via_entorn(monkeypatch):
    fp = _fp_real()  # fingerprint real amb l'entorn net (abans de fixar-ne cap)
    # Fingerprint de confiança erroni via entorn → load_signed_allowlist el rebutja.
    monkeypatch.setenv("KERNEL_TRUSTED_GPG_FINGERPRINT", "DEADBEEF" * 5)
    with pytest.raises(AllowlistError):
        load_signed_allowlist(
            data_path=f"{AL}/tools.yaml", sig_path=f"{AL}/tools.yaml.sig", pubkey_path=f"{AL}/pubkey.asc",
        )
    # Amb el fingerprint correcte via entorn → carrega OK.
    monkeypatch.setenv("KERNEL_TRUSTED_GPG_FINGERPRINT", fp)
    al = load_signed_allowlist(
        data_path=f"{AL}/tools.yaml", sig_path=f"{AL}/tools.yaml.sig", pubkey_path=f"{AL}/pubkey.asc",
    )
    assert al.fingerprint
