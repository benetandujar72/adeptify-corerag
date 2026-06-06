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


class McpPinError(KernelError):
    """Servidor MCP sense pin conegut o amb hash que no coincideix (K3.3)."""


class ProvenanceError(KernelError):
    """Fragment RAG sense procedència vàlida o amb hash alterat (K8.4)."""


class SandboxError(KernelError):
    """Error en el sandbox d'execució (F2 · K4.x)."""


class ApprovalRequired(KernelError):
    """Acció de risc ≥2 proposada sense aprovació humana vàlida (F3 · K6.1).

    NO és un error de fallada: és l'ESCALAT a humà (l'humà al bucle). Porta la
    `ApprovalRequest` (amb el resum en llenguatge natural) perquè un humà decideixi.
    El kernel NO executa res mentre l'estat sigui PENDING_APPROVAL.
    """

    def __init__(self, request: object) -> None:
        self.request = request
        rid = getattr(request, "request_id", "?")
        tool_id = getattr(request, "tool_id", "?")
        req_n = getattr(request, "aprovacions_requerides", "?")
        super().__init__(
            f"PENDING_APPROVAL: «{tool_id}» requereix {req_n} aprovació(ns) humana(es) "
            f"(request_id={rid[:12] if isinstance(rid, str) else rid}…)"
        )


class ApprovalError(KernelError):
    """Token d'aprovació invàlid, caducat o que no lliga amb l'acció (F3 · K6.1)."""


class ApprovalRateLimited(KernelError):
    """Anti-fatiga d'aprovacions: aprovador en cooldown o supera el llindar (F3 · K6.4)."""


class PlaybookError(KernelError):
    """Playbook fora del registre signat, signatura invàlida, esquema de params
    incorrecte, o intent de materialitzar un Plan no conforme (F4 · K10 / INV-4)."""


class SchedulerError(KernelError):
    """Tasca programada invàlida, signatura incorrecta o playbook inexistent (F4 · K11)."""


class AgentDefError(KernelError):
    """Definició d'agent fora del registre signat o graf de coordinació no conforme
    (F4 · K13 / INV-4): cap agent s'instancia/modifica en runtime sense definició signada."""


class TascaError(KernelError):
    """Tasca automatitzada amb transició d'estat il·legal, propietari no coincident
    (confused-deputy) o PII evident (F5 · K14): la memòria de tasques és fail-closed."""


class IntencioError(KernelError):
    """Intenció conversacional que no resol a cap playbook del catàleg signat, o que
    s'intenta executar sense passar per propose→confirm (F5 · K13·F5a / K16)."""


class TriggerError(KernelError):
    """Trigger declaratiu invàlid: signatura incorrecta, playbook inexistent, operador no
    permès, o snapshot amb valors no numèrics (F5 · K15). L'avaluació és pura i propose-only."""


class SizingError(KernelError):
    """Catàleg de dimensionament de models malformat (K5 · Sub-A/llmfit): `params_b` o
    `quantitzacions` absents/invàlids. El motor de fit és pur i propose-only."""
