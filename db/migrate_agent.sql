-- Module 5: conversational agent. One ongoing conversation thread per user
-- (messages appended as a JSON array), resumed whenever they reconnect.
CREATE TABLE IF NOT EXISTS agent_conversations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    messages JSONB NOT NULL DEFAULT '[]',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- The agent's read-only Postgres role is created/granted at backend startup
-- (see scraper/agent/db_access.py, ensure_readonly_role) rather than here,
-- since its password comes from an env var and must never be committed to
-- a SQL file in git.
