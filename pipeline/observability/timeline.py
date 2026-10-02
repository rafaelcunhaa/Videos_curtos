"""Timeline — consulta simples por job/video."""
import json
from pathlib import Path
from typing import List

class Timeline:
    def __init__(self, path: str = ".pipeline_cache/audit_events.jsonl"):
        self.path = Path(path)

    def get_job_timeline(self, job_id: str) -> List[dict]:
        if not self.path.exists():
            return []
        results = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line=line.strip()
                if not line: continue
                evt = json.loads(line)
                if evt.get("job_id") == job_id:
                    results.append(evt)
        results.sort(key=lambda x: x.get("timestamp", ""))
        return results

    def get_video_timeline(self, video_id: str) -> List[dict]:
        if not self.path.exists():
            return []
        results = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line=line.strip()
                if not line: continue
                evt = json.loads(line)
                if evt.get("video_id") == video_id:
                    results.append(evt)
        results.sort(key=lambda x: x.get("timestamp", ""))
        return results

    def get_recent_events(self, limit: int = 50) -> List[dict]:
        if not self.path.exists():
            return []
        results = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line=line.strip()
                if not line: continue
                results.append(json.loads(line))
        results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return results[:limit]
