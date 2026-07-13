import psycopg2
import os
from contextlib import contextmanager


def required_env(name: str) -> str:
    """Read a required env var with no fallback.

    DB_HOST and DB_PASSWORD used to default to "localhost"/"0000" - fine for
    nothing in particular, since every real setup (docker-compose's env_file,
    the README's local-dev instructions) already sets them explicitly. The
    only thing a silent default did was mask a missing .env by quietly
    connecting to the wrong host or a guessable password instead of failing
    loudly.
    """
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not set - copy .env.example to .env and fill it in")
    return value


def get_conn():
    return psycopg2.connect(
        host=required_env("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "realestate"),
        user=os.getenv("DB_USER", "postgres"),
        password=required_env("DB_PASSWORD"),
    )


@contextmanager
def db_cursor(commit: bool = False):
    """Yield a cursor from a fresh connection, guaranteeing the connection is
    always closed - even if the query raises - instead of leaking until GC
    (a bare get_conn()/cur.close()/conn.close() sequence skips the close
    calls entirely when cur.execute() raises). Pass commit=True for
    INSERT/UPDATE/DELETE; leave it False for SELECT-only callers.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()