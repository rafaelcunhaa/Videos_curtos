"""JobRepository — persistência de jobs, separada de regra de negócio."""
import sqlite3, json
from pathlib import Path
from .base import BaseRepository

class JobRepository(BaseRepository):
    def __init__(self, db_path: str = "banco_shorts.db"):
        self.db_path = db_path

    def _conn(self):
        import sqlite3
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def get_by_id(self, job_id: str):
        conn = self._conn()
        try:
            cur = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_pending(self):
        conn = self._conn()
        try:
            cur = conn.execute("SELECT * FROM jobs WHERE state IN ('pending','running') ORDER BY created_at")
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def update_state(self, job_id: str, state: str):
        conn = self._conn()
        try:
            conn.execute("UPDATE jobs SET state = ?, updated_at = datetime('now') WHERE id = ?", (state, job_id))
            conn.commit()
        finally:
            conn.close()
