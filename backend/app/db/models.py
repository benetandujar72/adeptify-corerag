"""Models ORM (SQLAlchemy 2.0) que reflecteixen `db/init/01_schema.sql`.

Taules: documents, chunks (amb columna vector(1024)), conversations, messages,
audit_log, feedback. El tipus de columna del vector és `pgvector.Vector`; en
entorns sense l'extensió pgvector (p. ex. SQLite en tests) es degrada a un
tipus genèric perquè la importació no falli.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON as JSONType
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings


class Embedding(TypeDecorator):
    """Tipus de columna d'embedding portable entre Postgres (pgvector) i SQLite.

    A Postgres usa `vector(dim)` real (operadors de distància nadius). A SQLite
    (tests) es degrada a JSON, prou per emmagatzemar i recuperar el vector sense
    necessitar l'extensió pgvector.

    El `Comparator` exposa `cosine_distance` perquè el retriever pugui ordenar
    per similitud cosinus amb l'operador `<=>` de pgvector. A SQLite l'operador
    no existeix; el retriever ja captura l'error i recau en cerca sense ordre
    vectorial (els tests reordenen amb el reranker doble).
    """

    impl = JSONType
    cache_ok = True

    class Comparator(TypeDecorator.Comparator):
        """Delega les distàncies vectorials als operadors de pgvector.

        El costat dret es coacciona al tipus `vector` de pgvector perquè el
        bind processor el formati correctament (`'[...]'::vector`).
        """

        def _vec(self, other):
            from sqlalchemy import type_coerce

            try:
                from pgvector.sqlalchemy import Vector

                return type_coerce(other, Vector())
            except Exception:  # pragma: no cover - pgvector absent
                return other

        def cosine_distance(self, other):
            return self.op("<=>", return_type=Float)(self._vec(other))

        def l2_distance(self, other):
            return self.op("<->", return_type=Float)(self._vec(other))

        def max_inner_product(self, other):
            return self.op("<#>", return_type=Float)(self._vec(other))

    comparator_factory = Comparator

    def __init__(self, dim: int) -> None:
        super().__init__()
        self._dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            try:
                from pgvector.sqlalchemy import Vector

                return dialect.type_descriptor(Vector(self._dim))
            except Exception:  # pragma: no cover - pgvector absent
                return dialect.type_descriptor(JSONType())
        return dialect.type_descriptor(JSONType())


_VECTOR_TYPE = Embedding(get_settings().embedding_dim)


def _uuid() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    """Base declarativa comuna."""


class Document(Base):
    """Document ingerit (PDF/DOCX/MD/HTML)."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    doc_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    institucio_id: Mapped[str] = mapped_column(String(64), index=True, default="nou_patufet")
    filename: Mapped[str] = mapped_column(String(512))
    tipus: Mapped[str] = mapped_column(String(16))  # pdf | docx | xlsx | md | html
    versio: Mapped[str] = mapped_column(String(32), default="1")
    verificat_el: Mapped[str | None] = mapped_column(String(32), nullable=True)
    n_chunks: Mapped[int] = mapped_column(Integer, default=0)
    estat: Mapped[str] = mapped_column(String(32), default="indexat")
    # Visibilitat per rol: "tots" (qualsevol rol intern) | "admin" (només
    # direcció/PAS/superadmin) — p. ex. documentació de gestió de l'aplicació.
    visibilitat: Mapped[str] = mapped_column(String(16), default="tots", index=True)
    # Namespace d'aïllament FÍSIC (Qdrant) / LÒGIC (pgvector). Mai delegat al
    # prompt: filtre obligatori a la capa de dades. Per defecte 'intern' (canal
    # autenticat). Documents marcats 'publico' (FAQ general, calendari, info
    # institucional) accessibles via /api/public/chat sense autenticació.
    namespace: Mapped[str] = mapped_column(String(32), default="intern", index=True)
    # Metadades per al RAG/CAG i la governança de sortida externa. `canal_rag`
    # separa currículum, materials docents, documents de centre i dades sensibles.
    origen: Mapped[str] = mapped_column(String(32), default="manual", index=True)
    canal_rag: Mapped[str] = mapped_column(String(48), default="rag_materials_docents", index=True)
    sensibilitat: Mapped[str] = mapped_column(String(32), default="docent", index=True)
    exportable_ia: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    metadades: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    creat_el: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(Base):
    """Fragment de text amb el seu embedding (bge-m3, 1024-dim)."""

    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    contingut: Mapped[str] = mapped_column(Text)
    pagina: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ordre: Mapped[int] = mapped_column(Integer, default=0)
    embedding = mapped_column(_VECTOR_TYPE, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="chunks")


class DocumentOriginal(Base):
    """Còpia del fitxer ORIGINAL ingerit, per poder obrir/descarregar la font citada
    (F1, docs/20). Taula separada de `documents` perquè el blob NO carregui les
    consultes habituals. Aïllament: `institucio_id` (defensa en profunditat)."""

    __tablename__ = "document_originals"

    doc_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    institucio_id: Mapped[str] = mapped_column(String(64), index=True, default="nou_patufet")
    filename: Mapped[str] = mapped_column(String(512))
    mime: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    mida: Mapped[int] = mapped_column(Integer, default=0)
    contingut: Mapped[bytes] = mapped_column(LargeBinary)
    creat_el: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Conversation(Base):
    """Conversa (memòria conversacional per conversation_id)."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    titol: Mapped[str] = mapped_column(String(256), default="Nova conversa")
    agent_id: Mapped[str] = mapped_column(String(64))
    etiqueta: Mapped[str | None] = mapped_column(String(128), nullable=True)
    institucio_id: Mapped[str] = mapped_column(String(64), index=True, default="nou_patufet")
    usuari: Mapped[str] = mapped_column(String(128), index=True)
    rol: Mapped[str] = mapped_column(String(32))
    creat_el: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    actualitzat_el: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.creat_el",
    )


class Message(Base):
    """Missatge dins d'una conversa (user | assistant)."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    rol: Mapped[str] = mapped_column(String(16))  # user | assistant
    contingut: Mapped[str] = mapped_column(Text)
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fonts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    confianca: Mapped[float | None] = mapped_column(Float, nullable=True)
    creat_el: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class AuditLog(Base):
    """Registre d'auditoria append-only (no s'actualitza ni s'esborra)."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    usuari: Mapped[str] = mapped_column(String(128), index=True)
    rol: Mapped[str] = mapped_column(String(32))
    accio: Mapped[str] = mapped_column(String(64))
    agent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detalls: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    creat_el: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Institucio(Base):
    """Institució (tenant). Cada institució té el seu RAG AÏLLAT: documents,
    usuaris i converses propis, més la seva configuració i branding."""

    __tablename__ = "institucions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    nom: Mapped[str] = mapped_column(String(256))
    actiu: Mapped[bool] = mapped_column(default=True)
    # config: { llm_model, agents_actius: [...], rag_top_k, reranker_actiu, ... }
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # branding: { logo_url, color_primari, color_secundari, ... }
    branding: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    creat_el: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class User(Base):
    """Usuari registrat de la plataforma (login amb contrasenya + rol RBAC).

    El `username` és únic PER INSTITUCIÓ (no globalment): pot existir un
    `direccio` a `nou_patufet` i un altre `direccio` a `cic`.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", "institucio_id", name="uq_user_username_inst"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(128), index=True)  # únic per institució
    password_hash: Mapped[str] = mapped_column(String(256))
    rol: Mapped[str] = mapped_column(String(32))
    institucio_id: Mapped[str] = mapped_column(String(64), index=True, default="nou_patufet")
    nom: Mapped[str | None] = mapped_column(String(256), nullable=True)
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    actiu: Mapped[bool] = mapped_column(default=True)
    # Versió de token: en incrementar-la s'invaliden TOTS els JWT emesos abans
    # (logout, canvi de contrasenya, desactivació). El token porta la claim `tv`
    # i `get_current_user` la compara amb aquest valor.
    token_version: Mapped[int] = mapped_column(default=0)
    # MFA/2FA (TOTP). `totp_secret` = clau base32 (⚠️ xifrar en repòs a producció,
    # com JWT_SECRET; diferit). `totp_actiu` = l'usuari ha completat l'enrolment.
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_actiu: Mapped[bool] = mapped_column(default=False)
    # Idioma preferit de la UI: ca | es | eu. Per defecte català (centre catalanoparlant).
    # Es respecta a la propera sessió (el frontend el llegeix amb /api/auth/me).
    idioma: Mapped[str] = mapped_column(String(8), default="ca")
    creat_el: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ultim_acces: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TelegramBinding(Base):
    """Vinculació segura entre un xat de Telegram i un usuari del sistema.

    Zero-trust: el bot mai serveix dades fins que un humà ha vinculat el seu
    chat_id a un compte autenticat via magic link (`vincle_token` + caducitat).
    Després, el bot opera sempre amb el rol verificat (`rol`) i la institució
    (`institucio_id`), aplicats al filtre obligatori de la capa de dades.
    """

    __tablename__ = "telegram_bindings"

    chat_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    usuari: Mapped[str] = mapped_column(String(128), index=True)
    institucio_id: Mapped[str] = mapped_column(String(64), index=True)
    rol: Mapped[str] = mapped_column(String(32))
    creat_el: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    vincle_token: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    vincle_caduca: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actiu: Mapped[bool] = mapped_column(default=True)


class Feedback(Base):
    """Valoració d'una resposta (👍 útil / 👎 millorar)."""

    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    message_id: Mapped[str] = mapped_column(String(64), index=True)
    valor: Mapped[str] = mapped_column(String(16))  # util | millorar
    comentari: Mapped[str | None] = mapped_column(Text, nullable=True)
    usuari: Mapped[str | None] = mapped_column(String(128), nullable=True)
    institucio_id: Mapped[str] = mapped_column(String(64), index=True, default="nou_patufet")
    creat_el: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
