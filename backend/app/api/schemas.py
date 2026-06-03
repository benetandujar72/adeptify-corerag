"""Esquemes Pydantic que implementen EXACTAMENT els models de API_CONTRACT.md.

Els noms de camp són en català per coincidir amb el contracte (nom, descripcio,
rols_permesos, fonts, confianca, etc.).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TipusDoc = Literal["pdf", "docx", "xlsx", "md", "html", "image"]
RolMissatge = Literal["user", "assistant"]


# ───────────────────────── Models de dades ──────────────────────────────────


class Agent(BaseModel):
    """Agent especialitzat (mockup 02)."""

    id: str
    nom: str
    descripcio: str
    color: str  # per a la UI
    rols_permesos: list[str]


class Font(BaseModel):
    """Font citada (panell dret del dashboard)."""

    doc_id: str
    filename: str
    tipus: TipusDoc
    pagina: int | None = None
    fragments: int = 1
    score: float = 0.0
    verificat_el: str | None = None
    snippet: str | None = None


class Missatge(BaseModel):
    """Missatge d'una conversa."""

    id: str
    rol: RolMissatge
    contingut: str
    agent_id: str | None = None
    fonts: list[Font] | None = None
    confianca: float | None = None
    creat_el: str
    # Proposta d'acció d'escriptura preparada per l'assistent agèntic (no executada;
    # la UI ofereix un botó de confirmació). No es persisteix: és efímera del torn.
    proposta: dict | None = None


class Conversa(BaseModel):
    """Resum d'una conversa per al sidebar."""

    id: str
    titol: str
    agent_id: str
    etiqueta: str | None = None
    actualitzat_el: str
    n_missatges: int


class DocumentEstat(BaseModel):
    """Document indexat (per a GET /api/documents): Font sense pàgina/score."""

    doc_id: str
    filename: str
    tipus: TipusDoc
    fragments: int = 0
    verificat_el: str | None = None
    estat: str = "indexat"
    origen: str = "manual"
    canal_rag: str = "rag_materials_docents"
    sensibilitat: str = "docent"
    exportable_ia: bool = False
    metadades: dict | None = None


# ───────────────────────── Peticions / respostes ────────────────────────────


class ChatRequest(BaseModel):
    """Cos de POST /api/chat."""

    agent_id: str
    conversation_id: str | None = None
    # Límit de mida: evita amplificació de recursos (embeddings/LLM) i DoS amb
    # preguntes desmesurades. 8000 caràcters cobreix de sobres una consulta real.
    message: str = Field(..., max_length=8000)
    stream: bool = True


class RecursSuggerit(BaseModel):
    """Recurs de documentació verificat que el SISTEMA suggereix (F2, docs/20).

    Mai prové de l'LLM: surt del registre curat (`recursos_documentacio`), filtrat per
    tema, institució i visibilitat. `doc_id` (si tipus="document") es baixa amb la
    descàrrega F1 (RBAC); `url` (si tipus="url") és un enllaç oficial verificat.
    """

    id: str
    titol: str
    descripcio: str = ""
    tipus: str = "url"
    url: str | None = None
    doc_id: str | None = None
    versio: str = ""
    font_oficial: str = ""


class ChatResponse(BaseModel):
    """Resposta de POST /api/chat quan stream=false."""

    conversation_id: str
    message: Missatge
    agent_utilitzat: str
    recursos_suggerits: list[RecursSuggerit] = []


class AgentsResponse(BaseModel):
    agents: list[Agent]


class ConversationsResponse(BaseModel):
    conversations: list[Conversa]


class ConversationDetailResponse(BaseModel):
    conversation: Conversa
    messages: list[Missatge]


class DocumentsResponse(BaseModel):
    documents: list[DocumentEstat]


class IngestRequest(BaseModel):
    """Cos de POST /api/ingest quan és JSON (alternativa al multipart)."""

    path: str | None = None


class IngestResponse(BaseModel):
    job_id: str
    estat: str


class IngestStatusResponse(BaseModel):
    estat: Literal["processant", "fet", "error", "encuat"]
    documents: int = 0
    chunks: int = 0
    detall: str | None = None


class FeedbackRequest(BaseModel):
    message_id: str
    valor: Literal["util", "millorar"]
    comentari: str | None = None


class LoginRequest(BaseModel):
    usuari: str
    contrasenya: str | None = None
    rol: str | None = None  # ignorat si l'usuari existeix (el rol surt del registre)
    # Slug del centre on validar-se. Resol l'ambigüitat de noms repetits entre
    # institucions (p. ex. un `direccio` per centre). El frontend l'envia després
    # de la pantalla de selecció d'institució.
    institucio: str | None = None
    # Codi TOTP (6 dígits) si l'usuari té MFA activat (segon pas del login).
    codi_mfa: str | None = None


class LoginResponse(BaseModel):
    token: str
    rol: str
    # Si és cert, les credencials són correctes però cal un segon pas: el codi MFA.
    # El frontend mostra el camp de codi i torna a enviar el login amb `codi_mfa`.
    mfa_required: bool = False


class MfaSetupResponse(BaseModel):
    """Resposta de l'inici d'enrolment MFA: secret per a entrada manual + URI per al QR."""

    secret: str
    otpauth_uri: str


class MfaCodi(BaseModel):
    codi: str


class MfaEstat(BaseModel):
    actiu: bool


class InstitucioPublica(BaseModel):
    """Info MÍNIMA d'una institució per a la pantalla de selecció (pre-login).

    Públic (sense auth): NOMÉS slug, nom i branding (cap dada sensible ni config).
    """

    slug: str
    nom: str
    branding: dict | None = None


class InstitucionsPubliquesResponse(BaseModel):
    institucions: list[InstitucioPublica]


class MeResponse(BaseModel):
    usuari: str
    rol: str
    idioma: str = "ca"  # ca | es | eu


class IdiomaUpdate(BaseModel):
    idioma: str  # ca | es | eu


# ───────────────────────── Administració (superadmin) ───────────────────────


class UserOut(BaseModel):
    """Usuari (sense la contrasenya)."""

    username: str
    rol: str
    nom: str | None = None
    email: str | None = None
    actiu: bool = True
    institucio_id: str = "nou_patufet"
    creat_el: str | None = None
    ultim_acces: str | None = None


class UsersResponse(BaseModel):
    users: list[UserOut]


class UserCreate(BaseModel):
    username: str
    contrasenya: str
    rol: str
    nom: str | None = None
    email: str | None = None
    actiu: bool = True
    institucio_id: str = "nou_patufet"


class UserUpdate(BaseModel):
    rol: str | None = None
    nom: str | None = None
    email: str | None = None
    actiu: bool | None = None
    contrasenya: str | None = None


class AuditEntry(BaseModel):
    id: str
    usuari: str
    rol: str
    accio: str
    agent: str | None = None
    conversation_id: str | None = None
    detalls: dict | None = None
    creat_el: str


class AuditResponse(BaseModel):
    entrades: list[AuditEntry]
    total: int


# ───────────────────────── Institucions (multi-tenant) ──────────────────────


class InstitucioOut(BaseModel):
    slug: str
    nom: str
    actiu: bool = True
    config: dict | None = None
    branding: dict | None = None
    creat_el: str | None = None


class InstitucionsResponse(BaseModel):
    institucions: list[InstitucioOut]


class InstitucioCreate(BaseModel):
    slug: str
    nom: str
    config: dict | None = None
    branding: dict | None = None


class InstitucioUpdate(BaseModel):
    nom: str | None = None
    actiu: bool | None = None
    config: dict | None = None
    branding: dict | None = None


# ─────────────────── Integracions externes (Fase 4 — Google) ────────────────


class GoogleIntegracioOut(BaseModel):
    """Config de Google per a la UI (secrets EMMASCARATS)."""

    actiu: bool = False
    auth_mode: str = "service_account"  # service_account | oauth
    project_id: str = ""
    workspace_domain: str = ""
    sa_subject: str = ""
    client_id: str = ""
    redirect_uri: str = ""
    scopes: list[str] = []
    drive_folders: list[str] = []
    calendar_ids: list[str] = []
    gmail_sender: str = ""
    gmail_comptes: list[str] = []  # comptes de correu autoritzats (allow-list)
    # Indicadors (no es retorna mai el valor del secret)
    sa_json_set: bool = False
    client_secret_set: bool = False


class GoogleIntegracioUpdate(BaseModel):
    """Actualització de la config de Google. Els secrets només s'apliquen si venen."""

    actiu: bool | None = None
    auth_mode: str | None = None
    project_id: str | None = None
    workspace_domain: str | None = None
    sa_subject: str | None = None
    client_id: str | None = None
    redirect_uri: str | None = None
    scopes: list[str] | None = None
    drive_folders: list[str] | None = None
    calendar_ids: list[str] | None = None
    gmail_sender: str | None = None
    gmail_comptes: list[str] | None = None
    # Secrets (write-only)
    sa_json: str | None = None
    client_secret: str | None = None


class LmsIntegracioOut(BaseModel):
    actiu: bool = False
    moodle_actiu: bool = False
    moodle_base_url: str = ""
    moodle_course_ids: list[str] = []
    moodle_token_set: bool = False
    classroom_actiu: bool = False
    classroom_course_ids: list[str] = []
    ingesta_entregues: bool = False


class LmsIntegracioUpdate(BaseModel):
    actiu: bool | None = None
    moodle_actiu: bool | None = None
    moodle_base_url: str | None = None
    moodle_course_ids: list[str] | None = None
    moodle_token: str | None = None
    classroom_actiu: bool | None = None
    classroom_course_ids: list[str] | None = None
    ingesta_entregues: bool | None = None


class LmsMaterialOut(BaseModel):
    id: str
    titol: str
    tipus: str = "material"
    descripcio: str = ""
    url: str | None = None
    mime: str | None = None
    filename: str | None = None


class IntegracioTestResult(BaseModel):
    ok: bool
    estat: str  # desactivat | incomplet | llibreries_absents | ok | error_auth | oauth_pendent
    detall: str


# ───────────────────────── Accés de xarxa per institució ─────────────────────


class AccesXarxaOut(BaseModel):
    """Política d'accés per IP/CIDR de la institució (lectura per a la UI)."""

    actiu: bool = False
    cidrs_lan: list[str] = []
    ips_permeses: list[str] = []
    actualitzat_el: str | None = None
    actualitzat_per: str | None = None
    # Camps informatius (no s'editen): IP del peticionari i si entraria amb la política actual.
    ip_actual: str | None = None
    ip_actual_permesa: bool = True


class AccesXarxaUpdate(BaseModel):
    """Edició: tots els camps són opcionals; només es modifiquen els enviats."""

    actiu: bool | None = None
    cidrs_lan: list[str] | None = None
    ips_permeses: list[str] | None = None


class DeteccioXarxaResponse(BaseModel):
    """Resposta del botó «Detecta xarxa local»."""

    ip_actual: str | None = None
    es_local: bool = False
    cidr_suggerit: str | None = None
    missatge: str


# ───────────────────────── Estat del sistema ────────────────────────────────


class StatusServidor(BaseModel):
    actiu: bool
    host: str
    entorn: str


class StatusIndexacio(BaseModel):
    al_dia: bool
    documents: int
    ultima: str | None = None


class StatusPrivadesa(BaseModel):
    processament_local: bool
    crides_externes: int
    xifratge: str
    auditat_el: str


class StatusModel(BaseModel):
    nom: str
    backend: str
    catala: str


class SystemStatusResponse(BaseModel):
    servidor: StatusServidor
    indexacio: StatusIndexacio
    privadesa: StatusPrivadesa
    model: StatusModel
    versio: str


# ───────────────────────── Errors ───────────────────────────────────────────


class ErrorDetall(BaseModel):
    codi: Literal["FORBIDDEN", "NOT_FOUND", "RATE_LIMIT", "INTERNAL", "BAD_REQUEST"]
    missatge: str


class ErrorResponse(BaseModel):
    error: ErrorDetall
