import sqlite3
import os
import json
from datetime import datetime
from typing import Dict, Any, Optional, List

class SQLiteStateStore:
    def __init__(self, db_path: str = "erasmus_state.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initializes state and audit tables if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_executions (
                    task_id TEXT PRIMARY KEY,
                    user_request TEXT NOT NULL,
                    tool_name TEXT,
                    status TEXT NOT NULL,
                    reason TEXT,
                    payload_hash TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(task_id) REFERENCES task_executions(task_id)
                )
            """)
            conn.commit()

    def create_task(self, task_id: str, user_request: str) -> None:
        """Records initial task state on ingress."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO task_executions (task_id, user_request, status) VALUES (?, ?, ?)",
                (task_id, user_request, "INGRESS")
            )
            cursor.execute(
                "INSERT INTO audit_logs (task_id, event_type, details) VALUES (?, ?, ?)",
                (task_id, "TASK_CREATED", json.dumps({"request": user_request}))
            )
            conn.commit()

    def update_task(self, task_id: str, status: str, tool_name: Optional[str] = None, 
                    reason: Optional[str] = None, payload_hash: Optional[str] = None) -> None:
        """Updates current state and appends audit trail."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute("""
                UPDATE task_executions 
                SET status = ?, tool_name = COALESCE(?, tool_name), reason = ?, 
                    payload_hash = COALESCE(?, payload_hash), updated_at = ?
                WHERE task_id = ?
            """, (status, tool_name, reason, payload_hash, now, task_id))

            audit_details = json.dumps({"status": status, "tool": tool_name, "reason": reason})
            cursor.execute(
                "INSERT INTO audit_logs (task_id, event_type, details) VALUES (?, ?, ?)",
                (task_id, f"STATE_{status}", audit_details)
            )
            conn.commit()

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single task execution record."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM task_executions WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_audit_trail(self, task_id: str) -> List[Dict[str, Any]]:
        """Retrieves complete chronological audit events for a given task."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audit_logs WHERE task_id = ? ORDER BY id ASC", (task_id,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
