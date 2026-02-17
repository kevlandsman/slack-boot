from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional


class ConversationStateManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self):
        schema_path = Path(__file__).parent.parent / "db" / "schema.sql"
        with open(schema_path) as f:
            schema_sql = f.read()
        conn = self._get_conn()
        try:
            conn.executescript(schema_sql)
            conn.commit()
        finally:
            conn.close()

    def create_conversation(
        self,
        slack_thread: str,
        channel_id: str,
        user_id: str,
        skill_name: Optional[str] = None,
        state: Optional[dict] = None,
        llm_provider: str = "local",
    ) -> str:
        conv_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO conversations
                   (id, slack_thread, channel_id, user_id, skill_name, state, llm_provider, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    conv_id,
                    slack_thread,
                    channel_id,
                    user_id,
                    skill_name,
                    json.dumps(state or {}),
                    llm_provider,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return conv_id

    def get_conversation_by_thread(self, slack_thread: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM conversations WHERE slack_thread = ?",
                (slack_thread,),
            ).fetchone()
            if row:
                result = dict(row)
                result["state"] = json.loads(result["state"]) if result["state"] else {}
                return result
            return None
        finally:
            conn.close()

    def get_conversation(self, conv_id: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conv_id,)
            ).fetchone()
            if row:
                result = dict(row)
                result["state"] = json.loads(result["state"]) if result["state"] else {}
                return result
            return None
        finally:
            conn.close()

    def update_conversation(self, conv_id: str, **kwargs):
        conn = self._get_conn()
        try:
            sets = []
            values = []
            for key, value in kwargs.items():
                if key == "state":
                    value = json.dumps(value)
                sets.append(f"{key} = ?")
                values.append(value)
            sets.append("updated_at = ?")
            values.append(datetime.utcnow().isoformat())
            values.append(conv_id)
            conn.execute(
                f"UPDATE conversations SET {', '.join(sets)} WHERE id = ?",
                values,
            )
            conn.commit()
        finally:
            conn.close()

    def add_message(self, conversation_id: str, role: str, content: str):
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO messages (conversation_id, role, content, timestamp)
                   VALUES (?, ?, ?, ?)""",
                (conversation_id, role, content, datetime.utcnow().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    def get_messages(self, conversation_id: str) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT role, content, timestamp FROM messages WHERE conversation_id = ? ORDER BY timestamp",
                (conversation_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_active_conversations_for_channel(self, channel_id: str) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT * FROM conversations
                   WHERE channel_id = ? AND skill_name IS NOT NULL
                   ORDER BY updated_at DESC""",
                (channel_id,),
            ).fetchall()
            results = []
            for row in rows:
                r = dict(row)
                state = json.loads(r["state"]) if r["state"] else {}
                # Completed skills should not capture future unrelated messages.
                if state.get("phase") == "complete":
                    continue
                r["state"] = state
                results.append(r)
            return results
        finally:
            conn.close()
