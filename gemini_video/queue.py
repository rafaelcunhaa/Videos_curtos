import sqlite3
from pathlib import Path
from datetime import datetime
from .models import SceneSpec
from .errors import QuotaError

DB = Path("gemini_video/data/jobs.db")

class JobStore:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(DB))
        self._create()

    def _create(self):
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS gemini_scene_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT, scene_id TEXT, prompt TEXT,
            model TEXT, status TEXT DEFAULT 'PENDING',
            operation_id TEXT, output_path TEXT, attempts INTEGER DEFAULT 0,
            created_at TEXT, updated_at TEXT, next_retry_at TEXT,
            last_error TEXT, error_type TEXT, completed_at TEXT,
            UNIQUE(video_id, scene_id)
        )""")
        self.conn.commit()

    def save(self, spec: SceneSpec, status: str = "PENDING", error: str = None):
        self.conn.execute(
            "INSERT OR IGNORE INTO gemini_scene_jobs (video_id, scene_id, prompt, model, status, created_at, updated_at, last_error, error_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (spec.video_id, spec.scene_id, spec.prompt, "veo", status, datetime.now().isoformat(), datetime.now().isoformat(), error, "QUOTA" if "quota" in (error or "").lower() else None)
        )
        self.conn.commit()

    def update(self, scene_id: str, status: str, operation_id: str = None, error: str = None):
        self.conn.execute(
            "UPDATE gemini_scene_jobs SET status=?, operation_id=?, updated_at=?, last_error=? WHERE scene_id=?",
            (status, operation_id, datetime.now().isoformat(), error, scene_id)
        )
        self.conn.commit()

    def list_by_video(self, video_id: str):
        cur = self.conn.execute("SELECT * FROM gemini_scene_jobs WHERE video_id=?", (video_id,))
        return cur.fetchall()

    def get_by_scene(self, scene_id: str):
        cur = self.conn.execute("SELECT * FROM gemini_scene_jobs WHERE scene_id=?", (scene_id,))
        return cur.fetchone()

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, cooldown_minutes: int = 30):
        self.failures = 0
        self.threshold = failure_threshold
        self.cooldown = cooldown_minutes
        self.state = "CLOSED"

    def record_failure(self):
        self.failures += 1
        if self.failures >= self.threshold:
            self.state = "OPEN"

    def record_success(self):
        self.failures = 0
        self.state = "CLOSED"

    def allow_request(self) -> bool:
        return self.state == "CLOSED"
