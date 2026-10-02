import json
from repositories.publication_repository import PublicationRepository
from pipeline.publication_service import PublicationService, PublicationStatus


def service(tmp_path):
    return PublicationService(PublicationRepository(str(tmp_path / "pub.jsonl")))


def test_normal_publication_and_idempotency(tmp_path):
    svc = service(tmp_path)
    first = svc.begin("job-1", "artifact-1", "youtube")
    second = svc.begin("job-1", "artifact-1", "youtube")
    assert first["publication_key"] == second["publication_key"]
    assert second["status"] == PublicationStatus.IN_PROGRESS
    done = svc.succeed("job-1", "artifact-1", "youtube", "yt-123")
    assert done["status"] == PublicationStatus.PUBLISHED
    assert done["external_id"] == "yt-123"


def test_timeout_is_unknown_until_reconciled(tmp_path):
    svc = service(tmp_path)
    svc.begin("job-2", "artifact-2", "youtube")
    unknown = svc.fail("job-2", "artifact-2", "youtube", "TIMEOUT", "response lost", unknown=True)
    assert unknown["status"] == PublicationStatus.UNKNOWN
    assert svc.reconcile("job-2", "artifact-2", "youtube", lambda: "yt-existing")["status"] == PublicationStatus.PUBLISHED


def test_platforms_are_independent(tmp_path):
    svc = service(tmp_path)
    svc.begin("job-3", "artifact-3", "youtube")
    svc.begin("job-3", "artifact-3", "tiktok")
    svc.succeed("job-3", "artifact-3", "youtube", "yt-3")
    svc.fail("job-3", "artifact-3", "tiktok", "AUTH", "unauthorized")
    assert svc.repository.get(svc.key("job-3", "artifact-3", "youtube"))["status"] == "PUBLISHED"
    assert svc.repository.get(svc.key("job-3", "artifact-3", "tiktok"))["status"] == "FAILED"


def test_audit_events_are_safe(tmp_path):
    events = []
    class Audit:
        def record_event(self, event):
            events.append(event)
    svc = PublicationService(PublicationRepository(str(tmp_path / "pub.jsonl")), Audit())
    svc.begin("job-4", "artifact-4", "youtube")
    assert events[0]["event"] == "PUBLISH_STARTED"
    assert "token" not in json.dumps(events).lower()
