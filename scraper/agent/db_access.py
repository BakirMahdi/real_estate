"""Read-only Postgres access for the conversational agent's SQL tool.

The agent (an LLM) is allowed to write and run its own SELECT queries
against the properties table so it can answer open-ended questions a fixed
set of search filters can't ("average price per m2 in Sfax", "cheapest
3-bedroom houses near the coast", etc). Letting an LLM generate SQL is only
safe if the blast radius of a bad or adversarial query is bounded at the
database level, not just by string-matching the query text:

  - it runs as a dedicated `agent_ro` Postgres role, created here on
    startup, that only ever has SELECT granted on `properties` - never on
    `users` (password hashes) or `agent_conversations` (other users'
    conversations). Postgres denies access to ungranted tables regardless
    of what the query text says.
  - the role's password is generated once and stored in a gitignored file
    (never in a committed SQL migration), so `db/migrate_agent.sql` doesn't
    carry a secret.
  - a per-role statement_timeout bounds runaway/expensive queries.

Statement-shape validation (single SELECT, no stacked statements) still
happens in db_tool.py as defense in depth, but the role grants are the real
backstop.
"""

import os
import secrets

from ..db import get_conn

AGENT_DB_USER = "agent_ro"
_DATA_DIR = os.getenv("DATA_DIR", "data")
_PASSWORD_FILE = os.path.join(_DATA_DIR, ".agent_ro_password")


def _load_or_create_password() -> str:
    if os.path.exists(_PASSWORD_FILE):
        with open(_PASSWORD_FILE, "r") as f:
            return f.read().strip()
    os.makedirs(_DATA_DIR, exist_ok=True)
    password = secrets.token_urlsafe(32)
    with open(_PASSWORD_FILE, "w") as f:
        f.write(password)
    return password


def ensure_readonly_role() -> str:
    """Create/repair the agent_ro role and its grants. Idempotent; call on API startup.

    Returns the role's password (also cached on disk so it survives restarts
    without changing - a changed password would orphan the role's ability to
    log in until updated everywhere).
    """
    password = _load_or_create_password()

    conn = get_conn()
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (AGENT_DB_USER,))
        if cur.fetchone():
            cur.execute(
                f"ALTER ROLE {AGENT_DB_USER} WITH LOGIN PASSWORD %s", (password,)
            )
        else:
            cur.execute(
                f"CREATE ROLE {AGENT_DB_USER} WITH LOGIN PASSWORD %s "
                "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT",
                (password,),
            )
        cur.execute(f"ALTER ROLE {AGENT_DB_USER} SET statement_timeout = '5s'")

        # Explicit REVOKE first: if this role's grants ever drift (e.g. a
        # future migration does `GRANT ALL ON properties TO PUBLIC`), this
        # guarantees agent_ro ends up with exactly SELECT on properties,
        # nothing more, every time the backend starts.
        cur.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {AGENT_DB_USER}")
        cur.execute(f"GRANT CONNECT ON DATABASE {os.getenv('DB_NAME', 'realestate')} TO {AGENT_DB_USER}")
        cur.execute(f"GRANT USAGE ON SCHEMA public TO {AGENT_DB_USER}")
        cur.execute(f"GRANT SELECT ON properties TO {AGENT_DB_USER}")
        cur.close()
    finally:
        conn.close()

    return password


def get_readonly_conn():
    """Open a connection as agent_ro. Call ensure_readonly_role() at least once first."""
    import psycopg2

    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "realestate"),
        user=AGENT_DB_USER,
        password=_load_or_create_password(),
    )
