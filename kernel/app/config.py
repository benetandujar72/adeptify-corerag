"""Configuració del kernel (variables d'entorn, pydantic-settings).

Valors per defecte segurs per a dev/test. En desplegament real, sobreescriure via env.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class KernelSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False,
        protected_namespaces=(),  # permetem camps model_* (model_base_url, models_manifest_path)
    )

    entorn: str = "dev"  # dev | prod
    versio: str = "0.1.0-kernel-f1"

    # ── Confiança de signatures GPG (F4 · gate G-D) ──
    # Fingerprint FIXAT de la clau que ha de signar TOTS els artefactes (allowlist,
    # playbooks, schedule, agents). En PRODUCCIÓ el pinning és OBLIGATORI (fail-closed):
    # sense aquest valor, la verificació GPG es rebutja. Així no n'hi ha prou amb una
    # signatura vàlida de qualsevol clau importable.
    trusted_gpg_fingerprint: str | None = None

    # ── Límits del bucle determinista (K1.2) ──
    max_steps_default: int = 10
    max_steps_hard: int = 25  # sostre absolut; cap sessió pot demanar-ne més
    token_budget_default: int = 20000
    session_timeout_s: float = 120.0  # K1.4 timeout absolut

    # ── Capability tokens (K2.2) ──
    # El secret REAL viu al vault (KERNEL_CAPABILITY_SECRET); aquí només el TTL.
    capability_ttl_s: int = 120     # 60..300
    capability_ttl_min_s: int = 60
    capability_ttl_max_s: int = 300
    capability_issuer: str = "adeptify-kernel"
    capability_audience: str = "adeptify-tools"

    # ── Compuerta d'aprovació humana (F3 · K6.1/K6.4) ──
    # El secret REAL viu al vault (KERNEL_APPROVAL_SECRET); aquí només paràmetres.
    approval_token_ttl_s: int = 300       # vida del token d'aprovació humà
    approval_window_s: float = 60.0       # K6.4 finestra anti-fatiga
    approval_max_per_window: int = 5      # K6.4 màx. aprovacions per finestra (>5 → cooldown)
    approval_cooldown_s: float = 300.0    # K6.4 durada del cooldown
    approval_audience: str = "adeptify-approval"

    # ── Allowlist d'eines firmada GPG (K3.1) ──
    allowlist_path: str = "/app/allowlist/tools.yaml"
    allowlist_sig_path: str = "/app/allowlist/tools.yaml.sig"
    allowlist_pubkey_path: str = "/app/allowlist/pubkey.asc"

    # ── Router de models locals (K5.1/K5.2) — INV-3 ──
    # NOMÉS endpoints de la LAN aprovada. Mai proveïdors cloud.
    model_base_url: str = "http://ollama:11434/v1"
    lan_hosts: str = (
        "localhost,127.0.0.1,::1,ollama,vllm,host.docker.internal,kernel,kerneldb"
    )
    lan_cidrs: str = "127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7"
    models_manifest_path: str = "/app/allowlist/models.yaml"

    # ── Base de dades (K8.1 RLS) ──
    kernel_db_url: str = "postgresql://kernel_app:kernel_app@kerneldb:5432/kernel"

    @property
    def lan_hosts_list(self) -> list[str]:
        return [h.strip().lower() for h in (self.lan_hosts or "").split(",") if h.strip()]

    @property
    def lan_cidrs_list(self) -> list[str]:
        return [c.strip() for c in (self.lan_cidrs or "").split(",") if c.strip()]

    @property
    def es_prod(self) -> bool:
        return (self.entorn or "").lower() in {"prod", "prod-onprem", "prod-local"}


@lru_cache
def get_settings() -> KernelSettings:
    return KernelSettings()
