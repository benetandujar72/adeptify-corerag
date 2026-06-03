"""Fixtures de test: BD SQLite en memòria + dobles per a LLM/embeddings/reranker.

Els tests corren SENSE GPU ni models descarregats. Tots els components pesants
(client LLM, embeddings bge-m3, reranker bge) s'embeliquen amb dobles
deterministes. La BD és SQLite en memòria (compartida entre connexions via
StaticPool), de manera que no cal Postgres.
"""

from __future__ import annotations

import os

# Config d'entorn ABANS d'importar l'app (perquè get_settings la capturi).
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "secret-de-test")
os.environ.setdefault("ENTORN", "dev")
os.environ.setdefault("OPENAI_BASE_URL", "http://ollama:11434/v1")
os.environ.setdefault("AUDIT_LOG_PATH", "")  # desactiva escriptura a fitxer
# El control d'accés remot és una funcionalitat de DESPLEGAMENT (opt-in). El
# desactivem per defecte als tests (el TestClient no té IP real); el test dedicat
# `test_acces_remot.py` l'activa explícitament.
os.environ.setdefault("ACCES_REMOT_ADMIN_ONLY", "false")
# Confiança del X-Forwarded-For als tests: el TestClient envia "testclient" com a
# request.client.host (no és una IP vàlida). Si activem `proxy_de_confianca`,
# podem injectar la IP via XFF (vegeu el fixture `client`).
os.environ.setdefault("PROXY_DE_CONFIANCA", "true")

import datetime as dt  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _entorn_test():
    """Garanteix variables d'entorn coherents durant tota la sessió."""
    yield


@pytest.fixture()
def engine():
    """Motor SQLite en memòria compartit (StaticPool)."""
    from app.db.models import Base
    # CORE: les taules de domini escolar (models_domini) viuen a la SUITE; el
    # nucli només registra les taules base (users/documents/chunks/…).

    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def SessionLocal(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def db(SessionLocal):
    sessio = SessionLocal()
    try:
        yield sessio
    finally:
        sessio.close()


# ───────────────────────── Dobles deterministes ─────────────────────────────
#
# Els dobles viuen a `app.testing.fakes` perquè es comparteixin entre els tests
# (aquí) i el runner d'avaluació offline (`eval/run_eval.py --mock`), sense
# duplicar-los. Es reexporten amb el nom històric per no tocar la resta de tests.

from app.testing.fakes import FakeEmbedder, FakeLLM, FakeReranker  # noqa: E402


@pytest.fixture()
def fake_llm():
    return FakeLLM()


@pytest.fixture(autouse=True)
def injecta_dobles(fake_llm):
    """Injecta els dobles als singletons abans de cada test i neteja després."""
    from app.core import rate_limit, telemetria
    from app.rag import embeddings, llm, rerank

    embeddings.set_embedder(FakeEmbedder())
    rerank.set_reranker(FakeReranker())
    llm.set_llm_client(fake_llm)
    telemetria.reinicia()
    rate_limit.reinicia()  # estat en memòria del rate-limit del login
    yield
    embeddings.set_embedder(None)
    rerank.set_reranker(None)
    llm.set_llm_client(None)


@pytest.fixture()
def client(SessionLocal):
    """TestClient amb la dependència de BD redirigida a SQLite en memòria."""
    from app.db.session import get_db
    from app.main import crea_app

    app = crea_app()

    def _get_db_override():
        sessio = SessionLocal()
        try:
            yield sessio
        finally:
            sessio.close()

    app.dependency_overrides[get_db] = _get_db_override
    # El router de documents obre la seva pròpia sessió per a tasques de fons;
    # redirigim també el sessionmaker global perquè apunti a SQLite.
    import app.db.session as session_mod

    session_mod.get_sessionmaker = lambda: SessionLocal  # type: ignore[assignment]

    with TestClient(app) as c:
        # IP per defecte realista per a tots els tests (el TestClient envia
        # "testclient" com a request.client.host, que no és parsejable com a IP
        # i bloca la política d'accés de xarxa quan està activa). Els tests que
        # vulguin simular IP remota sobreescriuen explícitament aquesta capçalera.
        c.headers["X-Forwarded-For"] = "127.0.0.1"
        yield c


@pytest.fixture()
def token_docent():
    from app.core.roles import Rol
    from app.core.security import crea_token

    return crea_token("marta", Rol.DOCENT)


@pytest.fixture()
def token_familia():
    from app.core.roles import Rol
    from app.core.security import crea_token

    return crea_token("familia_garcia", Rol.FAMILIA)


@pytest.fixture()
def token_alumne():
    from app.core.roles import Rol
    from app.core.security import crea_token

    return crea_token("pol", Rol.ALUMNE)


@pytest.fixture()
def auth(token_docent):
    return {"Authorization": f"Bearer {token_docent}"}


@pytest.fixture()
def document_indexat(db):
    """Insereix un document amb un chunk i embedding fals a la BD de test."""
    from app.db.models import Chunk, Document
    from app.rag.embeddings import get_embedder

    doc = Document(
        doc_id="nofc_2024",
        filename="NOFC_2024.pdf",
        tipus="pdf",
        versio="1",
        verificat_el="2024-09-01",
        n_chunks=1,
        estat="indexat",
    )
    db.add(doc)
    db.flush()
    text = (
        "El curs d'esquí es fa del 15 al 19 de gener segons la circular SOR-001. "
        "Les sortides i el calendari escolar es regulen a les NOFC."
    )
    vec = get_embedder().embed([text])[0]
    db.add(
        Chunk(
            document_id=doc.id,
            contingut=text,
            pagina=12,
            ordre=0,
            embedding=vec,
        )
    )
    db.commit()
    return doc
