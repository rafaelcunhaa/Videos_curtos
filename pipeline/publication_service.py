"""Coordenação de publicação idempotente, sem SQL e sem lógica de provider."""
from __future__ import annotations

from typing import Any, Callable
from repositories.publication_repository import PublicationRepository


class PublicationStatus:
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    SCHEDULED = "SCHEDULED"


class PublicationService:
    def __init__(self, repository: PublicationRepository | None = None, audit: Any = None):
        self.repository = repository or PublicationRepository()
        self.audit = audit

    @staticmethod
    def key(job_id: str, artifact_id: str, platform: str) -> str:
        return f"{job_id}:{artifact_id}:{platform}"

    def begin(self, job_id: str, artifact_id: str, platform: str,
              video_id: str | None = None) -> dict[str, Any]:
        key = self.key(job_id, artifact_id, platform)
        current = self.repository.get(key)
        if current is not None:
            return current
        record = self.repository.create_or_get({
            "publication_key": key,
            "job_id": job_id,
            "artifact_id": artifact_id,
            "video_id": video_id,
            "platform": platform,
            "status": PublicationStatus.IN_PROGRESS,
            "attempt": 1,
        })
        self._audit(record, "PUBLISH_STARTED")
        return record

    def succeed(self, job_id: str, artifact_id: str, platform: str,
                external_id: str | None = None) -> dict[str, Any]:
        key = self.key(job_id, artifact_id, platform)
        record = self.repository.update(key, status=PublicationStatus.PUBLISHED,
                                        external_id=external_id)
        self._audit(record, "PUBLISH_COMPLETED")
        return record

    def fail(self, job_id: str, artifact_id: str, platform: str,
             error_type: str, message: str, unknown: bool = False) -> dict[str, Any]:
        key = self.key(job_id, artifact_id, platform)
        status = PublicationStatus.UNKNOWN if unknown else PublicationStatus.FAILED
        record = self.repository.update(key, status=status, error_type=error_type,
                                        message=message)
        self._audit(record, "PUBLISH_FAILED" if not unknown else "PUBLISH_UNKNOWN")
        return record

    def reconcile(self, job_id: str, artifact_id: str, platform: str,
                  lookup: Callable[[], str | None]) -> dict[str, Any]:
        """Consulta provider antes de qualquer repetição de estado UNKNOWN."""
        key = self.key(job_id, artifact_id, platform)
        record = self.repository.get(key)
        if record is None:
            raise KeyError(f"Publication not found: {key}")
        external_id = lookup()
        if external_id:
            return self.succeed(job_id, artifact_id, platform, external_id)
        return record

    def _audit(self, record: dict[str, Any], event: str) -> None:
        if self.audit is None:
            return
        self.audit.record_event({
            "event": event,
            "job_id": record.get("job_id"),
            "video_id": record.get("video_id"),
            "artifact_id": record.get("artifact_id"),
            "platform": record.get("platform"),
            "publication_key": record.get("publication_key"),
            "external_id": record.get("external_id"),
            "status": record.get("status"),
        })
