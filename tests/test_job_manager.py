"""
Testes para Job Manager — ETAPA 2 (Job State + Resume + Idempotência)

Regras:
- Não chamam APIs pagas
- Não alteram conteúdo de produção
- Usam mocks quando necessário
- Testam estados, resume, idempotência, retry
"""

import pytest
import json
import os
import time

# Garante que pipeline esteja disponível
import sys
sys.path.insert(0, ".")

from pipeline.job_models import (
    JobState,
    JobStage,
    STAGE_ORDER,
    JobRecord,
    JobMetadata,
    generate_job_id,
    TERMINAL_STATES,
    RETRYABLE_STATES,
)
from pipeline.job_manager import JobManager, job_enabled


class TestJobModels:
    def test_job_states_exist(self):
        """Todos os estados definidos existem."""
        expected = {
            "CREATED", "PLANNING", "SCRIPT_READY", "AUDIO_READY",
            "MEDIA_READY", "EDITING", "VALIDATING", "READY",
            "SCHEDULED", "PUBLISHED", "FAILED", "PAUSED",
            "RETRYING", "CANCELLED",
        }
        actual = {s.value for s in JobState}
        assert expected == actual

    def test_generate_job_id_unique(self):
        job1 = generate_job_id("183")
        time.sleep(0.01)
        job2 = generate_job_id("183")
        assert job1 != job2
        assert len(job1) > 10

    def test_stage_order(self):
        """Ordem é consistente."""
        assert len(STAGE_ORDER) > 0
        # Nenhum duplicado
        values = [s.value for s in STAGE_ORDER]
        assert len(values) == len(set(values))

    def test_record_stage_completed(self):
        record = JobRecord(video_id="test", job_id="j1")
        assert not record.is_stage_completed(JobStage.PLANNING)
        record.mark_stage_completed(JobStage.PLANNING)
        assert record.is_stage_completed(JobStage.PLANNING)
        # Idempotência: não adiciona duplicado
        prev_len = len(record.completed_stages)
        record.mark_stage_completed(JobStage.PLANNING)
        assert len(record.completed_stages) == prev_len

    def test_resume_point(self):
        record = JobRecord(video_id="t", job_id="j")
        # Nenhum estágio: resume do primeiro
        next_stage, skip = record.get_resume_point()
        assert next_stage == STAGE_ORDER[0]
        assert skip == []

        # Com estágios completos
        record.mark_stage_completed(JobStage.PLANNING)
        record.mark_stage_completed(JobStage.SCRIPT_GENERATION)
        next_stage, skip = record.get_resume_point()
        assert next_stage == JobStage.SCRIPT_VALIDATION
        assert len(skip) == 2

    def test_state_transitions(self):
        record = JobRecord(video_id="t", job_id="j")
        assert record.state == JobState.CREATED
        record.mark_stage_completed(JobStage.SCRIPT_GENERATION)
        assert record.state == JobState.SCRIPT_READY

    def test_failed_state(self):
        record = JobRecord(video_id="t", job_id="j")
        record.mark_failed(JobStage.RENDER, "timeout")
        assert record.state == JobState.FAILED
        assert record.last_error == "timeout"
        assert record.retry_count == 1

    def test_to_dict_from_dict(self):
        original = JobRecord(video_id="t", job_id="j")
        original.mark_stage_completed(JobStage.TTS_GENERATION)
        data = original.to_dict()
        restored = JobRecord.from_dict(data)
        assert restored.video_id == original.video_id
        assert restored.state == original.state
        assert JobStage.TTS_GENERATION.value in restored.completed_stages


class TestJobManager:
    def test_manager_disabled_by_default(self):
        """Por padrão, FEATURE_PIPELINE_STATE=false → desativado."""
        # Limpa env
        old = os.getenv("FEATURE_PIPELINE_STATE")
        if old is not None:
            del os.environ["FEATURE_PIPELINE_STATE"]
        assert job_enabled() is False
        # Restaura
        if old is not None:
            os.environ["FEATURE_PIPELINE_STATE"] = old

    def test_manager_custom_flag_true(self):
        os.environ["FEATURE_PIPELINE_STATE"] = "true"
        assert job_enabled() is True
        del os.environ["FEATURE_PIPELINE_STATE"]

    def test_manager_start_and_get_status(self):
        """Quando ativado, deve criar e consultar."""
        os.environ["FEATURE_PIPELINE_STATE"] = "true"
        try:
            manager = JobManager(video_id="test_99")
            job_id = manager.start(job_type="shorts")
            assert job_id is not None
            status = manager.get_status()
            assert status["video_id"] == "test_99"
            assert status["enabled"] is True
        finally:
            del os.environ["FEATURE_PIPELINE_STATE"]

    def test_idempotency_stage_complete(self):
        """Mesmo estágio não deve ser executado duas vezes."""
        os.environ["FEATURE_PIPELINE_STATE"] = "true"
        try:
            manager = JobManager(video_id="test_100")
            manager.start()
            manager.complete_stage(JobStage.PLANNING)
            # Chamada segunda não deve falhar
            ok = manager.complete_stage(JobStage.PLANNING)
            assert ok is True
            status = manager.get_status()
            assert status["completed_stages"].count("planning") == 1
        finally:
            del os.environ["FEATURE_PIPELINE_STATE"]

    def test_resume_returns_stage(self):
        """Resume deve apontar para próximo estágio."""
        os.environ["FEATURE_PIPELINE_STATE"] = "true"
        try:
            manager = JobManager(video_id="test_101")
            manager.start()
            manager.complete_stage(JobStage.PLANNING)
            manager.complete_stage(JobStage.SCRIPT_GENERATION)
            resume_stage = manager.resume()
            assert resume_stage == JobStage.SCRIPT_VALIDATION
        finally:
            del os.environ["FEATURE_PIPELINE_STATE"]

    def test_timeline_logged(self):
        os.environ["FEATURE_PIPELINE_STATE"] = "true"
        try:
            manager = JobManager(video_id="test_102")
            manager.start()
            timeline = manager.get_timeline()
            assert len(timeline) >= 1
            assert timeline[0]["event"] == "JOB_CREATED"
        finally:
            del os.environ["FEATURE_PIPELINE_STATE"]

    def test_fail_and_retry(self):
        os.environ["FEATURE_PIPELINE_STATE"] = "true"
        try:
            manager = JobManager(video_id="test_103")
            manager.start()
            manager.fail(JobStage.RENDER, "erro", retry_delay=None)
            # Sem retry_delay explicit, coletamos que tentou falhar
            assert manager.get_status()["state"] in ("FAILED", "PAUSED")
        finally:
            del os.environ["FEATURE_PIPELINE_STATE"]

    def test_can_proceed_true_for_active(self):
        os.environ["FEATURE_PIPELINE_STATE"] = "true"
        try:
            manager = JobManager(video_id="test_104")
            manager.start()
            assert manager.can_proceed() is True
        finally:
            del os.environ["FEATURE_PIPELINE_STATE"]


class TestRegression:
    """Testes de regressão: nenhuma alteração de pipeline existente."""

    def test_config_has_feature_flag(self):
        from config import Config
        cfg = Config()
        assert hasattr(cfg, "feature_pipeline_state")

    def test_banco_has_table(self):
        import sqlite3
        conn = sqlite3.connect("banco_shorts.db")
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pipeline_jobs'")
        assert cur.fetchone() is not None
        conn.close()
