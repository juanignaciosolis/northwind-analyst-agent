-- db/memory_schema.sql
CREATE SCHEMA IF NOT EXISTS agent_memory;

CREATE TABLE IF NOT EXISTS agent_memory.memory (
    memory_id   TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    project_id  TEXT NOT NULL DEFAULT '',
    course_id   TEXT NOT NULL DEFAULT '',
    session_id  TEXT NOT NULL DEFAULT '',
    kind        TEXT NOT NULL,
    key         TEXT NOT NULL,
    value_json  JSONB NOT NULL,
    source      TEXT NOT NULL,
    confidence  DOUBLE PRECISION NOT NULL,
    priority    INTEGER NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL,
    expires_at  TIMESTAMPTZ NULL,
    supersedes  TEXT NULL,
    status      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_memory_scope
    ON agent_memory.memory (user_id, project_id, course_id, session_id, status);