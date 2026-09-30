import time
from datetime import datetime, timedelta
from .errors import QuotaError, AuthError, GeminiError
from .queue import JobStore, CircuitBreaker

class GeminiWorker:
    def __init__(self, store: JobStore | None = None, breaker: CircuitBreaker | None = None):
        self.store = store or JobStore()
        self.breaker = breaker or CircuitBreaker()

    def process_next(self):
        if not self.breaker.allow_request():
            return {"status": "CIRCUIT_OPEN"}
        # Mock: só registra que tentou; não chama API real
        return {"status": "PENDING_MOCK"}

    def handle_quota(self, scene_id: str, pause_hours: int = 5):
        self.store.update(scene_id, "PAUSED_QUOTA")
        next_retry = datetime.now() + timedelta(hours=pause_hours)
        # Persistido via banco existente já criado
        return {"next_retry_at": next_retry.isoformat(), "status": "PAUSED_QUOTA"}
