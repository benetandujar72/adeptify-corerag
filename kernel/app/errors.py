"""Excepcions del kernel. Totes deriven de KernelError per a un maneig uniforme."""

from __future__ import annotations


class KernelError(Exception):
    """Base de tots els errors del kernel."""


class ImmutableViolation(KernelError):
    """Intent de mutar el context de sessió immutable (K1.3)."""


class StepLimitExceeded(KernelError):
    """S'ha superat el límit de passos del pla (K1.2)."""


class BudgetExceeded(KernelError):
    """S'ha superat el pressupost de tokens; cal escalar a humà (K1.2)."""


class SessionTimeout(KernelError):
    """S'ha superat el timeout absolut de sessió (K1.4)."""


class PolicyDenied(KernelError):
    """La política deny-by-default ha denegat l'acció (K2.1 / INV-2)."""


class CapabilityError(KernelError):
    """Capability token invàlid, caducat o amb claims incorrectes (K2.2)."""


class AllowlistError(KernelError):
    """Eina fora de l'allowlist signada, o signatura GPG invàlida (K3.1 / INV-4)."""


class SchemaValidationError(KernelError):
    """Args o resultat d'una eina no compleixen l'esquema (K3.2)."""


class ExternalEndpointError(KernelError):
    """Endpoint de model fora de la LAN aprovada (K5.1 / INV-3)."""


class ArbitraryCodeError(KernelError):
    """Intent d'executar codi arbitrari (INV-1)."""
