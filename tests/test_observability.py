import time, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.observability.audit import AuditTrail
from pipeline.observability.events import EventType
from pipeline.observability.models import AuditEvent

def test_audit_record_and_read():
    trail = AuditTrail(".pipeline_cache/test_audit.jsonl")
    trail.record(AuditEvent(
        event_id="t1", job_id="J1", video_id="V1", stage="tts",
        event=EventType.STAGE_STARTED.value, status="running",
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
    ))
    from pipeline.observability.timeline import Timeline
    tl = Timeline(".pipeline_cache/test_audit.jsonl")
    res = tl.get_job_timeline("J1")
    assert len(res) == 1
    assert res[0]["event"] == "STAGE_STARTED"

def test_sanitization():
    trail = AuditTrail()
    clean = trail.sanitize({"api_key":"secret","ok":"val","auth_token":"t"})
    assert clean["api_key"] == "[REDACTED]"
    assert clean["ok"] == "val"

def test_security_no_secrets_persisted():
    trail = AuditTrail(".pipeline_cache/test_audit_sec.jsonl")
    trail.record(AuditEvent(
        event_id="s1", job_id="J2",
        metadata={"password":"x","authorization":"y","msg":"ok"},
        event=EventType.JOB_CREATED.value, status="success",
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
    ))
    with open(".pipeline_cache/test_audit_sec.jsonl") as f:
        line = f.read()
    assert "[REDACTED]" in line
    assert "secret" not in line or "REDACTED" in line
