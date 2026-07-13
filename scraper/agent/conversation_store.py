"""Persistence for the agent's one-thread-per-user conversation."""

import json

from ..db import get_conn

# Keeps both the DB row and the per-turn payload sent to Gemini bounded - a
# never-truncated history would otherwise grow the JSONB column and the
# resend-everything-every-turn request forever. 40 messages is 20 user/model
# turns, comfortably more context than a real support-style conversation
# needs.
MAX_HISTORY_MESSAGES = 40


def load_messages(user_id: int) -> list[dict]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT messages FROM agent_conversations WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
        messages = row[0] if row else []
        return messages[-MAX_HISTORY_MESSAGES:]
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
        # Trim in a second, simple statement rather than folding the slice
        # into the jsonb concatenation above - Postgres has no negative-index
        # array slicing, and this keeps the merge-then-cap logic readable.
        cur.execute(
            """
            UPDATE agent_conversations
            SET messages = (
                SELECT jsonb_agg(elem ORDER BY ord ASC)
                FROM (
                    SELECT elem, ord
                    FROM jsonb_array_elements(messages) WITH ORDINALITY AS t(elem, ord)
                    ORDER BY ord DESC
                    LIMIT %s
                ) AS last_n
            )
            WHERE user_id = %s AND jsonb_array_length(messages) > %s
            """,
            (MAX_HISTORY_MESSAGES, user_id, MAX_HISTORY_MESSAGES),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()
