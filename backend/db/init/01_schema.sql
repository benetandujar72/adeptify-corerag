-- ───────── adeptify-corerag · esquema inicial (Postgres 16 + pgvector) ─────────
-- S'executa automàticament en arrencar el contenidor `db` (docker-entrypoint-initdb.d).
-- Vector store amb embeddings bge-m3 (1024 dimensions).
-- NUCLI: només taules base (documents/chunks/converses/missatges/auditoria/feedback).
-- Les taules de domini escolar (alumnes, copilot_*, avaluacions…) viuen a la SUITE.

CREATE EXTENSION IF NOT EXISTS vector;

-- ── Documents ingerits ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id            TEXT PRIMARY KEY,
    doc_id        TEXT UNIQUE NOT NULL,           -- identificador estable (slug)
    filename      TEXT NOT NULL,
    tipus         TEXT NOT NULL,                  -- pdf | docx | xlsx | md | html
    versio        TEXT NOT NULL DEFAULT '1',
    verificat_el  TEXT,                           -- metadada de versió (data)
    n_chunks      INTEGER NOT NULL DEFAULT 0,
    estat         TEXT NOT NULL DEFAULT 'indexat',
    creat_el      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Chunks amb embedding vectorial ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chunks (
    id           TEXT PRIMARY KEY,
    document_id  TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    contingut    TEXT NOT NULL,
    pagina       INTEGER,
    ordre        INTEGER NOT NULL DEFAULT 0,
    embedding    vector(1024)                     -- bge-m3
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);

-- Índex ANN per a la cerca per similitud cosinus (HNSW).
-- Requereix pgvector >= 0.5. Si la versió és inferior, ometre aquest índex
-- (la cerca seqüencial funciona igualment al MVP).
DO $$
BEGIN
    BEGIN
        CREATE INDEX IF NOT EXISTS idx_chunks_embedding
            ON chunks USING hnsw (embedding vector_cosine_ops);
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'No s''ha pogut crear l''índex HNSW (pgvector antic?): %', SQLERRM;
    END;
END $$;

-- ── Converses i missatges (memòria conversacional) ───────────────────────────
CREATE TABLE IF NOT EXISTS conversations (
    id              TEXT PRIMARY KEY,
    titol           TEXT NOT NULL DEFAULT 'Nova conversa',
    agent_id        TEXT NOT NULL,
    etiqueta        TEXT,
    usuari          TEXT NOT NULL,
    rol             TEXT NOT NULL,
    creat_el        TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualitzat_el  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conversations_usuari ON conversations(usuari);
CREATE INDEX IF NOT EXISTS idx_conversations_actualitzat ON conversations(actualitzat_el DESC);

CREATE TABLE IF NOT EXISTS messages (
    id               TEXT PRIMARY KEY,
    conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    rol              TEXT NOT NULL,               -- user | assistant
    contingut        TEXT NOT NULL,
    agent_id         TEXT,
    fonts            JSONB,
    confianca        DOUBLE PRECISION,
    creat_el         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);

-- ── Registre d'auditoria (append-only) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id               TEXT PRIMARY KEY,
    usuari           TEXT NOT NULL,
    rol              TEXT NOT NULL,
    accio            TEXT NOT NULL,
    agent            TEXT,
    conversation_id  TEXT,
    detalls          JSONB,
    creat_el         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_usuari ON audit_log(usuari);
CREATE INDEX IF NOT EXISTS idx_audit_creat ON audit_log(creat_el DESC);

-- Append-only: revoquem UPDATE i DELETE per a l'usuari de l'aplicació.
DO $$
BEGIN
    BEGIN
        REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'No s''han pogut revocar privilegis sobre audit_log: %', SQLERRM;
    END;
END $$;

-- ── Feedback de respostes ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS feedback (
    id          TEXT PRIMARY KEY,
    message_id  TEXT NOT NULL,
    valor       TEXT NOT NULL,                    -- util | millorar
    comentari   TEXT,
    usuari      TEXT,
    creat_el    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feedback_message ON feedback(message_id);

-- ── Immutabilitat de l'auditoria (append-only de debò) ───────────────────────
-- El REVOKE de més amunt no afecta el rol PROPIETARI de la taula. Aquest trigger
-- impedeix UPDATE/DELETE sobre audit_log per a QUALSEVOL rol (defensa-en-profunditat
-- forense). Les insercions segueixen permeses.
CREATE OR REPLACE FUNCTION audit_log_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log és append-only: operació % no permesa', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_log_immutable ON audit_log;
CREATE TRIGGER trg_audit_log_immutable
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();
