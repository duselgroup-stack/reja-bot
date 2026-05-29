"""
SQLite Database - Vazifalar va foydalanuvchilar uchun
"""

import sqlite3
from datetime import datetime
from typing import Optional


class Database:
    def __init__(self, db_path: str = "tasks.db"):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    deadline TEXT DEFAULT '',
                    priority TEXT DEFAULT 'o''rta',
                    done INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    done_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    time_str TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
            """)

    def ensure_user(self, user_id: int, name: str):
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (id, name) VALUES (?, ?)",
                (user_id, name)
            )

    def get_all_users(self) -> list:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM users").fetchall()
            return [dict(r) for r in rows]

    # ── TASKS ──────────────────────────────

    def add_task(self, user_id: int, title: str, description: str = "",
                 deadline: str = "", priority: str = "o'rta") -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO tasks (user_id, title, description, deadline, priority) VALUES (?, ?, ?, ?, ?)",
                (user_id, title, description, deadline, priority)
            )
            return cursor.lastrowid

    def get_tasks(self, user_id: int, done: Optional[bool] = None) -> list:
        with self._connect() as conn:
            if done is None:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE user_id = ? ORDER BY priority DESC, created_at",
                    (user_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE user_id = ? AND done = ? ORDER BY priority DESC, created_at",
                    (user_id, 1 if done else 0)
                ).fetchall()
            return [dict(r) for r in rows]

    def mark_done(self, user_id: int, task_id: int) -> Optional[dict]:
        with self._connect() as conn:
            task = conn.execute(
                "SELECT * FROM tasks WHERE id = ? AND user_id = ?",
                (task_id, user_id)
            ).fetchone()
            if task:
                conn.execute(
                    "UPDATE tasks SET done = 1, done_at = ? WHERE id = ?",
                    (datetime.now().isoformat(), task_id)
                )
                return dict(task)
            return None

    def clear_done_tasks(self, user_id: int) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM tasks WHERE user_id = ? AND done = 1",
                (user_id,)
            )
            return cursor.rowcount

    def clear_all_tasks(self, user_id: int):
        with self._connect() as conn:
            conn.execute("DELETE FROM tasks WHERE user_id = ?", (user_id,))

    # ── REMINDERS ──────────────────────────

    def add_reminder(self, user_id: int, time_str: str, message: str):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO reminders (user_id, time_str, message) VALUES (?, ?, ?)",
                (user_id, time_str, message)
            )

    def get_reminders(self, user_id: int) -> list:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE user_id = ? ORDER BY time_str",
                (user_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ── CONVERSATIONS ──────────────────────

    def save_conversation(self, user_id: int, role: str, content: str):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversations (user_id, role, content) VALUES (?, ?, ?)",
                (user_id, role, content)
            )
            # Oxirgi 20 ta xabarni saqlash
            conn.execute("""
                DELETE FROM conversations WHERE id NOT IN (
                    SELECT id FROM conversations
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT 20
                ) AND user_id = ?
            """, (user_id, user_id))

    def get_conversation(self, user_id: int, limit: int = 10) -> list:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM conversations WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit)
            ).fetchall()
            return list(reversed([dict(r) for r in rows]))
