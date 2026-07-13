"""Persistence for the agent's one-thread-per-user conversation."""

import json

from ..db import get_conn


def load_messages(user_id: int) -> list[dict]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT messages FROM agent_conversations WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
        return row[0] if row else []
    finally:
        conn.close()


def append_messages(user_id: int, new_messages: list[dict]) -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO agent_conversations (user_id, messages, updated_at)
            VALUES (%s, %s::jsonb, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id) DO UPDATE
            SET messages = agent_conversations.messages || EXCLUDED.messages,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, json.dumps(new_messages)),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()
