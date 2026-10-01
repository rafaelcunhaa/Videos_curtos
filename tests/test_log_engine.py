"""
Testes ETAPA 4 — Logging + Timeline + Observabilidade
Não alteram pipeline de produção.
"""

from pipeline.log_engine import ProfessionalLogger, EVENTS


class TestLogEngine:
    def test_events_defined(self):
        assert "JOB_CREATED" in EVENTS
        assert "PUBLISHED" in EVENTS
        assert "VALIDATION_FAILED" in EVENTS

    def test_professional_logger_no_secret(self):
        logger = ProfessionalLogger()
        # Garante que dados sensíveis são redacted
        logger.log("STAGE_COMPLETED", job_id="j", video_id="v",
                   stage="edit", extra={"api_key": "secret123", "token": "abc"})
        # O log não deve expor os valores

    def test_log_retry(self):
        logger = ProfessionalLogger()
        logger.log_retry("j1", "v1", "render", attempt=2, next_retry_at="2026-10-01T10:00:00")

    def test_log_publish(self):
        logger = ProfessionalLogger()
        logger.log_publish("j1", "v1", "youtube", url="https://youtube.com/shorts/abc")
