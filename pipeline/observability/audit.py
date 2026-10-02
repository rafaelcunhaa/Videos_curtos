"""AuditTrail — persistência + sanitização de secrets."""
import re, json
from pathlib import Path
from .models import AuditEvent
from .events import EventType

SECRET_PATTERNS = re.compile(r"(?i)(api[_-]?key|token|password|authorization|cookie|secret|credential)")

class AuditTrail:
    def __init__(self, store_path: str = ".pipeline_cache/audit_events.jsonl"):
        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def sanitize(metadata: dict) -> dict:
        clean = {}
        for k, v in metadata.items():
            ks = str(k).lower()
            if SECRET_PATTERNS.search(ks) or (isinstance(v, str) and SECRET_PATTERNS.search(v)):
                clean[k] = "[REDACTED]"
            else:
                clean[k] = v
        return clean

    def record(self, event: AuditEvent) -> None:
        event.metadata = self.sanitize(event.metadata)
        with self.store_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "event_id": event.event_id,
                "job_id": event.job_id,
                "video_id": event.video_id,
                "stage": event.stage,
                "event": event.event,
                "status": event.status,
                "timestamp": event.timestamp,
                "duration_ms": event.duration_ms,
                "provider": event.provider,
                "error_type": event.error_type,
                "message": event.message,
                "metadata": event.metadata,
            }, ensure_ascii=False) + "\n")

    def start_stage(self, job_id: str, stage: str, video_id: str = None, provider: str = None):
        import time
        self.record(AuditEvent(
            event_id=f"{job_id}-{stage}-start",
            job_id=job_id, video_id=video_id, stage=stage,
            event=EventType.STAGE_STARTED.value, status="running",
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            provider=provider,
        ))

    def complete_stage(self, job_id: str, stage: str, status: str = "success",
                       duration_ms: int = None, video_id: str = None, provider: str = None, message: str = None):
        import time
        evt = EventType.STAGE_COMPLETED.value if status == "success" else EventType.STAGE_FAILED.value
        self.record(AuditEvent(
            event_id=f"{job_id}-{stage}-end",
            job_id=job_id, video_id=video_id, stage=stage,
            event=evt, status=status,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            duration_ms=duration_ms, provider=provider, message=message,
        ))
