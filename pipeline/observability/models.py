"""Modelo de evento de auditoria — pequeno, estruturado."""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class AuditEvent:
    event_id: str
    job_id: str
    video_id: Optional[str] = None
    stage: Optional[str] = None
    event: str = ""
    status: str = ""          # success / failed / skipped / running
    timestamp: str = ""        # ISO
    duration_ms: Optional[int] = None
    provider: Optional[str] = None
    error_type: Optional[str] = None
    message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
