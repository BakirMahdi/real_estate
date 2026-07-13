import psycopg2
import os
from contextlib import contextmanager

def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "realestate"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "0000")
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