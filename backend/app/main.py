"""Aplicació FastAPI principal — adeptify-corerag (backend del nucli obert).

Munta els routers del NUCLI (RAG/CAG + plataforma base), registra els handlers
d'error i crea/migra les taules base a l'arrencada (best-effort). Els mòduls de
gestió escolar (matrícula, avaluació, pagaments…) viuen al repositori privat
`adeptify-suiterag` i consumeixen aquest core per una API local autenticada.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import errors
from app.api.routes_admin import router as admin_router
from app.api.routes_audio import router as audio_router
from app.api.routes_auth import router as auth_router
from app.api.routes_chat import router as chat_router
from app.api.routes_conversations import router as conversations_router
from app.api.routes_documents import router as documents_router
from app.api.routes_codi_font import router as codi_font_router
from app.api.routes_feedback import router as feedback_router
from app.api.routes_institucio_seguretat import router as institucio_seguretat_router
from app.api.routes_institucio_users import router as institucio_users_router
from app.api.routes_public import router as public_router
from app.api.routes_servei import router as servei_router
from app.api.routes_system import router as system_router


def _crea_taules() -> None:
    """Crea les taules ORM del nucli si la BD és accessible (best-effort)."""
    try:
        from app.db.models import Base
        from app.db.session import get_engine

        Base.metadata.create_all(bind=get_engine())
    except Exception:
        # En dev/test sense BD viva, no bloquegem l'arrencada.
        pass


def _migra() -> None:
    """Migracions idempotents de les taules BASE (només Postgres).

    `create_all` crea taules noves però NO altera les existents; aquí afegim les
    columnes multi-tenant i de governança RAG a les taules del nucli (users,
    documents, conversations, feedback). Les taules de domini escolar (alumnes,
    copilot_*, onboarding_*, telegram_bindings…) NO pertanyen al nucli: les migra
    `adeptify-suiterag` sobre la seva pròpia base de dades.
    """
    try:
        from sqlalchemy import text

        from app.db.session import get_engine

        engine = get_engine()
        if engine.dialect.name != "postgresql":
            return
        sentencies = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS institucio_id VARCHAR(64) DEFAULT 'nou_patufet'",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS institucio_id VARCHAR(64) DEFAULT 'nou_patufet'",
            "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS institucio_id VARCHAR(64) DEFAULT 'nou_patufet'",
            "UPDATE users SET institucio_id='nou_patufet' WHERE institucio_id IS NULL",
            "UPDATE documents SET institucio_id='nou_patufet' WHERE institucio_id IS NULL",
            "UPDATE conversations SET institucio_id='nou_patufet' WHERE institucio_id IS NULL",
            # Visibilitat documental (docs de gestió només per a admin/direcció).
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS visibilitat VARCHAR(16) DEFAULT 'tots'",
            "UPDATE documents SET visibilitat='tots' WHERE visibilitat IS NULL",
            # username únic PER INSTITUCIÓ (no global): dos 'direccio' de centres diferents.
            "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_username_key",
            "DROP INDEX IF EXISTS ix_users_username",
            "CREATE INDEX IF NOT EXISTS ix_users_username ON users (username)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_username_inst ON users (username, institucio_id)",
            # MFA/2FA (TOTP).
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret VARCHAR(64)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_actiu BOOLEAN DEFAULT FALSE",
            "UPDATE users SET totp_actiu=FALSE WHERE totp_actiu IS NULL",
            # Revocació de tokens (logout/canvi de contrasenya/desactivació).
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER DEFAULT 0",
            "UPDATE users SET token_version=0 WHERE token_version IS NULL",
            # Feedback per institució (defense-in-depth multi-tenant).
            "ALTER TABLE feedback ADD COLUMN IF NOT EXISTS institucio_id VARCHAR(64) DEFAULT 'nou_patufet'",
            "UPDATE feedback SET institucio_id='nou_patufet' WHERE institucio_id IS NULL",
            "CREATE INDEX IF NOT EXISTS ix_feedback_institucio_id ON feedback (institucio_id)",
            # i18n: idioma preferit per usuari (ca per defecte).
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS idioma VARCHAR(8) DEFAULT 'ca'",
            "UPDATE users SET idioma='ca' WHERE idioma IS NULL",
            # Aïllament per namespace (canal públic vs. canal intern).
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS namespace VARCHAR(32) DEFAULT 'intern'",
            "UPDATE documents SET namespace='intern' WHERE namespace IS NULL",
            "CREATE INDEX IF NOT EXISTS ix_documents_namespace ON documents (namespace)",
            # Metadades RAG/CAG i governança de sortida externa.
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS origen VARCHAR(32) DEFAULT 'manual'",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS canal_rag VARCHAR(48) DEFAULT 'rag_materials_docents'",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS sensibilitat VARCHAR(32) DEFAULT 'docent'",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS exportable_ia BOOLEAN DEFAULT FALSE",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS metadades JSON",
            "UPDATE documents SET origen='manual' WHERE origen IS NULL",
            "UPDATE documents SET canal_rag='rag_materials_docents' WHERE canal_rag IS NULL",
            "UPDATE documents SET sensibilitat='docent' WHERE sensibilitat IS NULL",
            "UPDATE documents SET exportable_ia=FALSE WHERE exportable_ia IS NULL",
            "CREATE INDEX IF NOT EXISTS ix_documents_origen ON documents (origen)",
            "CREATE INDEX IF NOT EXISTS ix_documents_canal_rag ON documents (canal_rag)",
            "CREATE INDEX IF NOT EXISTS ix_documents_sensibilitat ON documents (sensibilitat)",
            "CREATE INDEX IF NOT EXISTS ix_documents_exportable_ia ON documents (exportable_ia)",
        ]
        with engine.begin() as conn:
            for s in sentencies:
                conn.execute(text(s))
    except Exception:
        pass


def _verifica_secrets_produccio() -> None:
    """Porta d'arrencada (fail-closed) per a entorns NO-dev.

    Avalua els controls de configuració (JWT_SECRET, token públic, inferència
    local, contrasenya de BD) i AVORTA l'arrencada si algun és `critic`. S'aplica
    a tot entorn que no sigui `dev` (pilot inclòs), de manera que un secret
    placeholder/feble mai pugui arrencar fora de desenvolupament. Els tests usen
    ENTORN=dev a propòsit, de manera que no els bloqueja.
    """
    from app.core.config import get_settings

    s = get_settings()
    if (s.entorn or "").lower() == "dev":
        return
    from app.security.produccio_check import controls_arrencada

    critics = [c for c in controls_arrencada(s) if c.severitat == "critic"]
    if critics:
        detall = "; ".join(
            f"{c.titol}: {c.detall}{(' → ' + c.recomanacio) if c.recomanacio else ''}"
            for c in critics
        )
        raise RuntimeError(f"Arrencada avortada (entorn={s.entorn}): {detall}")


class SecurityHeadersMiddleware:
    """Middleware ASGI lleuger que afegeix capçaleres de seguretat.

    És ASGI pur (no `BaseHTTPMiddleware`) a propòsit: `BaseHTTPMiddleware`
    bufferitza les respostes i trencaria l'streaming SSE de `/api/chat`.
    """

    _CAPCALERES = (
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"no-referrer"),
        (b"x-xss-protection", b"0"),
        # Els navegadors la ignoren sobre HTTP (LAN); s'aplica quan hi ha TLS al davant.
        (b"strict-transport-security", b"max-age=63072000; includeSubDomains"),
    )

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        async def _send(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                presents = {h[0].lower() for h in headers}
                for nom, valor in self._CAPCALERES:
                    if nom not in presents:
                        headers.append((nom, valor))
            await send(message)

        await self.app(scope, receive, _send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _verifica_secrets_produccio()
    _crea_taules()
    _migra()
    yield


def crea_app() -> FastAPI:
    """Factory de l'aplicació (facilita la creació en tests)."""
    from app.core.config import get_settings

    s = get_settings()
    # /docs, /redoc i /openapi.json: desactivats SEMPRE en producció (encara que
    # EXPOSA_DOCS sigui true), i controlats per EXPOSA_DOCS en dev/pilot.
    exposa_docs = s.exposa_docs and not s.es_prod

    app = FastAPI(
        title="adeptify-corerag — backend",
        version=__version__,
        description=(
            "Motor RAG/CAG self-hosted i multi-agent (nucli obert d'Adeptify). "
            "Tota la inferència és sobre models auto-allotjats; cap crida a "
            "APIs comercials de tercers."
        ),
        lifespan=lifespan,
        docs_url="/docs" if exposa_docs else None,
        redoc_url="/redoc" if exposa_docs else None,
        openapi_url="/openapi.json" if exposa_docs else None,
    )

    # Capçaleres de seguretat (ASGI pur, compatible amb SSE).
    app.add_middleware(SecurityHeadersMiddleware)

    origins = s.cors_origins_list
    permissiu = origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=not permissiu,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    errors.registra_handlers(app)

    # Routers del NUCLI (RAG/CAG + plataforma base).
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(system_router)
    app.include_router(chat_router)
    app.include_router(audio_router)
    app.include_router(conversations_router)
    app.include_router(documents_router)
    app.include_router(feedback_router)
    app.include_router(institucio_users_router)
    app.include_router(institucio_seguretat_router)
    app.include_router(public_router)
    app.include_router(codi_font_router)
    # Servei intern (suite → core): delegació d'inferència, autenticat amb
    # CORE_SERVICE_TOKEN. Desactivat si el secret no està configurat.
    app.include_router(servei_router)

    @app.get("/health", tags=["sistema"])
    def health() -> dict[str, str]:
        return {"estat": "ok", "versio": __version__}

    return app


app = crea_app()
