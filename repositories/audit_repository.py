"""AuditRepository — liga observability/ ao banco. Não conhece SQL de negócios."""
import sqlite3, json
from .base import BaseRepository

class AuditRepository(BaseRepository):
    def get_by_id(self, id):
        return self.get_job_timeline(id)
    def __init__(self, db_path: str = ".pipeline_cache/audit_events.jsonl"):
        # Uses JSONL (existing audit format) — can migrate to SQLite if needed
        self.store_path = db_path

    def record_event(self, event: dict):
        from pathlib import Path
        Path(self.store_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.store_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def get_job_timeline(self, job_id: str):
        results = []
        from pathlib import Path
        p = Path(self.store_path)
        if not p.exists(): return results
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                evt = json.loads(line.strip() or "{}")
                if evt.get("job_id") == job_id:
                    results.append(evt)
        results.sort(key=lambda x: x.get("timestamp", ""))
        return results
