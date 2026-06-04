-- K8.1 — Partició de memòria per tenant/sessió amb Row Level Security.
-- K9.1 — Auditoria append-only (RLS + trigger que rebutja UPDATE/DELETE).
-- L'app es connecta com a kernel_app (NO superusuari) → subjecte a RLS i a la
-- immutabilitat de l'auditoria. El tenant actiu es fixa amb SET app.tenant_id.

GRANT USAGE ON SCHEMA public TO kernel_app;

-- ─────────── Memòria de l'agent (aïllada per tenant) ───────────
CREATE TABLE IF NOT EXISTS agent_memory (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE agent_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_memory FORCE ROW LEVEL SECURITY;

-- Només files del tenant actiu (NULL si no s'ha fixat → cap fila).
CREATE POLICY mem_tenant ON agent_memory
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

GRANT SELECT, INSERT ON agent_memory TO kernel_app;

-- ─────────── Auditoria append-only amb hash encadenat ───────────
CREATE TABLE IF NOT EXISTS audit_log (
    seq        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ts         TIMESTAMPTZ NOT NULL DEFAULT now(),
    tenant_id  TEXT NOT NULL DEFAULT '',
    actor      TEXT NOT NULL,
    action     TEXT NOT NULL,
    payload    JSONB NOT NULL DEFAULT '{}'::jsonb,
    prev_hash  TEXT NOT NULL,
    hash       TEXT NOT NULL
);
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;

-- Lectura acotada per tenant; inserció lliure (cada actor escriu la seva traça).
CREATE POLICY audit_select ON audit_log FOR SELECT
    USING (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY audit_insert ON audit_log FOR INSERT
    WITH CHECK (true);

GRANT SELECT, INSERT ON audit_log TO kernel_app;
-- Append-only: ni l'app pot fer UPDATE/DELETE.
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM kernel_app;

-- Defensa en profunditat: trigger que rebutja UPDATE/DELETE per a QUALSEVOL rol.
CREATE OR REPLACE FUNCTION audit_no_mutate() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_log és append-only: UPDATE/DELETE no permès';
END;
$$;

CREATE TRIGGER audit_immutable
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_no_mutate();
