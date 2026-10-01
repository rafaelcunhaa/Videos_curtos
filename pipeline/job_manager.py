"""
Job Manager — Estado, Resume e Idempotência

Gerencia o ciclo de vida de jobs do pipeline de forma persistente.
Funcionalidade é opcional via FEATURE_PIPELINE_STATE.

Projeto de integrar mínima:
- Não altera comportamento existente quando desativado
- Usa banco.py (SQLite) para persistência
- Generico: não acoplado a providers específicos
"""

import logging
import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Imports do sistema
try:
    from banco import Banco
except ImportError:
    Banco = None  # Banco não disponível (ambiente de teste)

from .job_models import (
    JobRecord,
    JobState,
    JobStage,
    JobMetadata,
    STAGE_ORDER,
    STAGE_TO_STATE,
    TERMINAL_STATES,
    RETRYABLE_STATES,
    ACTIVE_STATES,
    generate_job_id,
)

from .log_engine import ProfessionalLogger

logger = logging.getLogger(__name__)
_professional_logger = ProfessionalLogger()


class JobManager:
    """
    Gerenciador de estado de jobs do pipeline.

    Fornece:
    - Criação e persistência de jobs
    - Transições de estado seguras
    - Resume a partir do último ponto
    - Idempotência por estágio
    - Retry controlado
    - Timeline de eventos

    Uso:
        manager = JobManager(video_id="183")
        manager.start()
        manager.update_state(JobState.PLANNING)
        if manager.is_stage_completed(JobStage.SCRIPT_GENERATION):
            return  # Já feito, não repetir
    """

    # Chave de idempotência prefixo
    CACHE_DIR = Path("./.pipeline_cache")
    TIMELINE_DIR = CACHE_DIR / "timeline"

    def __init__(self, video_id: str, db_path: str | None = None):
        self.video_id = str(video_id)
        self.db_path = db_path
        self._record: JobRecord | None = None
        self._ensure_dirs()

        # Verifica feature flag
        self.enabled = self._check_feature_flag()

    def _ensure_dirs(self) -> None:
        """Cria diretórios necessários."""
        self.CACHE_DIR.mkdir(exist_ok=True)
        self.TIMELINE_DIR.mkdir(parents=True, exist_ok=True)

    def _check_feature_flag(self) -> bool:
        """Verifica se o gerenciamento de estado está habilitado."""
        return os.getenv("FEATURE_PIPELINE_STATE", "false").lower() in ("true", "1", "yes")

    @property
    def record(self) -> JobRecord | None:
        """Retorna o registro deste job, carregando do banco se necessário."""
        if not self.enabled:
            return None
        if self._record is None:
            self._record = self._load_from_db()
        return self._record

    def _load_from_db(self) -> JobRecord | None:
        """Carrega job do banco de dados."""
        if Banco is None:
            return None
        try:
            db = Banco(self.db_path) if self.db_path else Banco()
            row = db.buscar_job_pipeline(self.video_id)
            if row:
                return JobRecord.from_dict(row)
        except Exception as e:
            logger.debug(f"Não foi possível carregar job {self.video_id}: {e}")
        return None

    def _save_to_db(self) -> bool:
        """Salva job no banco de dados."""
        if Banco is None or self._record is None:
            return False
        try:
            db = Banco(self.db_path) if self.db_path else Banco()
            db.salvar_job_pipeline(self._record.to_dict())
            return True
        except Exception as e:
            logger.error(f"Erro salvando job {self.video_id}: {e}")
            return False

    def start(self, job_type: str = "shorts", metadata: dict[str, Any] | None = None) -> str:
        """
        Inicia um novo job. Se já existir, reutiliza.

        Returns:
            job_id do job criado/reutilizado
        """
        if not self.enabled:
            return self.video_id  # Retorna video_id como fallback

        # Verifica se já existe job para este vídeo
        existing = self._load_from_db()
        if existing and existing.is_active and existing.state not in TERMINAL_STATES:
            logger.info(f"Job {self.video_id} já existe no estado {existing.state.value}, reaproveitando")
            self._record = existing
            return existing.job_id

        # Cria novo job
        job_id = generate_job_id(self.video_id)
        meta = JobMetadata(
            video_id=self.video_id,
            job_type=job_type,
            pipeline_version=self._get_pipeline_version(),
            **(metadata or {})
        )

        self._record = JobRecord(
            video_id=self.video_id,
            job_id=job_id,
            state=JobState.CREATED,
            metadata=meta,
        )

        self._save_to_db()
        self._log_event("JOB_CREATED", state=JobState.CREATED.value)
        _professional_logger.log("JOB_CREATED", job_id=self._record.job_id,
                                  video_id=self.video_id, stage="")
        logger.info(f"Job criado: {job_id} para vídeo {self.video_id}")
        return job_id

    def _get_pipeline_version(self) -> str:
        """Retorna versão atual do pipeline."""
        try:
            import pipeline
            return getattr(pipeline, "__version__", "2.0.0")
        except:
            return "2.0.0"

    def update_state(self, state: JobState, stage: JobStage | None = None,
                     error: str | None = None) -> bool:
        """
        Atualiza o estado do job.

        Args:
            state: Novo estado
            stage: Estágio (opcional, para marcar conclusão)
            error: Mensagem de erro (se falha)
        """
        if not self.enabled or self._record is None:
            return False

        old_state = self._record.state
        self._record.state = state
        self._record.updated_at = datetime.now()

        if error:
            self._record.last_error = error

        # Se stage foi fornecido, marca como concluído
        if stage:
            self._record.mark_stage_completed(stage)

        self._save_to_db()
        self._log_event("STATE_CHANGED",
                        old_state=old_state.value,
                        new_state=state.value,
                        stage=stage.value if stage else None,
                        error=error)
        logger.info(f"Job {self.video_id}: {old_state.value} → {state.value}")
        return True

    def complete_stage(self, stage: JobStage,
                       artifact_path: str | None = None,
                       metrics: dict[str, float] | None = None) -> bool:
        """
        Marca um estágio como concluído.

        Args:
            stage: Estágio concluído
            artifact_path: Caminho do artefato gerado (para cache/idempotência)
            metrics: Métricas de produção (duração, etc)
        """
        if not self.enabled or self._record is None:
            return False

        # Idempotência: não marca duas vezes
        if self._record.is_stage_completed(stage):
            logger.debug(f"Stage {stage.value} já concluído para job {self.video_id}")
            return True

        self._record.mark_stage_completed(stage, artifact_path)

        # Registra métricas
        if metrics:
            self._record.metadata.metrics.update(metrics)

        self._save_to_db()
        self._log_event("STAGE_COMPLETED", stage=stage.value, artifact=artifact_path)
        _professional_logger.log("STAGE_COMPLETED", job_id=self._record.job_id,
                                  video_id=self.video_id, stage=stage.value)

        # Atualiza estado macro baseado no estágio
        new_state = STAGE_TO_STATE.get(stage)
        if new_state and new_state not in TERMINAL_STATES:
            self._record.state = new_state
            self._save_to_db()

        return True

    def fail(self, stage: JobStage, error: str,
             retry_delay: timedelta | None = timedelta(hours=1)) -> bool:
        """
        Marca job como falhado em um estágio.

        Args:
            stage: Estágio que falhou
            error: Mensagem de erro
            retry_delay: Quando tentar novamente (None = não retry)
        """
        if not self.enabled or self._record is None:
            return False

        self._record.mark_failed(stage, error)

        if retry_delay:
            self._record.next_retry_at = datetime.now() + retry_delay
            # Se há retry_delay, marca como RETRYING se ainda não estiver final
            if self._record.state not in TERMINAL_STATES:
                self._record.state = JobState.RETRYING
        else:
            self._record.state = JobState.FAILED

        self._save_to_db()
        self._log_event("STAGE_FAILED", stage=stage.value, error=error,
                       retry_at=self._record.next_retry_at.isoformat() if self._record.next_retry_at else None)
        _professional_logger.log("FAILED", job_id=self._record.job_id,
                                  video_id=self.video_id, stage=stage.value,
                                  extra={"retry_at": self._record.next_retry_at.isoformat() if self._record.next_retry_at else None})
        logger.error(f"Job {self.video_id} falhou no stage {stage.value}: {error}")
        return True

    def pause(self, reason: str, pause_duration: timedelta | None = None) -> bool:
        """Pausa o job."""
        if not self.enabled or self._record is None:
            return False

        next_retry = datetime.now() + pause_duration if pause_duration else None
        self._record.mark_paused(reason, next_retry)
        self._save_to_db()
        self._log_event("JOB_PAUSED", reason=reason, next_retry=next_retry.isoformat() if next_retry else None)
        return True

    def resume(self) -> JobStage | None:
        """
        Retorna o próximo estágio para executar (ponto de resume).

        Returns:
            Próximo estágio a executar, ou None se todos concluídos
        """
        if not self.enabled or self._record is None:
            return None

        next_stage, skip_stages = self._record.get_resume_point()
        if next_stage:
            self._log_event("JOB_RESUME",
                          resume_from=next_stage.value,
                          skip_stages=[s.value for s in skip_stages])
            logger.info(f"Job {self.video_id}: retomando do estágio {next_stage.value}")
        return next_stage

    def is_stage_completed(self, stage: JobStage) -> bool:
        """Verifica se um estágio está completo (idempotência)."""
        if not self.enabled or self._record is None:
            return False
        return self._record.is_stage_completed(stage)

    def get_artifact(self, stage: JobStage) -> str | None:
        """Retorna o artefato gerado por um estágio."""
        if not self.enabled or self._record is None:
            return None
        return self._record.metadata.artifacts.get(stage.value)

    def get_status(self) -> dict[str, Any]:
        """Retorna status completo do job."""
        if not self.enabled or self._record is None:
            return {"enabled": False, "video_id": self.video_id}

        record = self._record
        return {
            "enabled": True,
            "video_id": record.video_id,
            "job_id": record.job_id,
            "state": record.state.value,
            "completed_stages": record.completed_stages,
            "last_stage_timestamp": record.stage_timestamps.get(record.completed_stages[-1]) if record.completed_stages else None,
            "last_error": record.last_error,
            "error_stage": record.error_stage,
            "retry_count": record.retry_count,
            "next_retry_at": record.next_retry_at.isoformat() if record.next_retry_at else None,
            "last_updated": record.updated_at.isoformat(),
            "created_at": record.created_at.isoformat(),
            "metadata": record.metadata.to_dict() if hasattr(record.metadata, 'to_dict') else {},
        }

    def should_retry(self) -> bool:
        """Verifica se o job deve tentar novamente baseado em next_retry_at."""
        if not self.enabled or self._record is None:
            return False
        if self._record.state not in RETRYABLE_STATES:
            return False
        if self._record.next_retry_at:
            return datetime.now() >= self._record.next_retry_at
        return True

    def can_proceed(self) -> bool:
        """Verifica se o job pode prosseguir (não está em estado bloqueador)."""
        if not self.enabled or self._record is None:
            return True  # Quando desativado, sempre permite
        return self._record.state not in {JobState.FAILED, JobState.CANCELLED}

    def cancel(self, reason: str = "cancelled_by_user") -> bool:
        """Cancela o job."""
        if not self.enabled or self._record is None:
            return False
        self._record.mark_cancelled(reason)
        self._save_to_db()
        self._log_event("JOB_CANCELLED", reason=reason)
        return True

    # ─── Timeline/Auditoria ───

    def _log_event(self, event: str, **kwargs: Any) -> None:
        """Registra evento na timeline do job (arquivo JSONL)."""
        if not self.enabled:
            return

        timeline_file = self.TIMELINE_DIR / f"{self.video_id}.jsonl"
        entry = {
            "timestamp": datetime.now().isoformat(),
            "video_id": self.video_id,
            "job_id": self._record.job_id if self._record else generate_job_id(self.video_id),
            "event": event,
            "data": kwargs,
        }

        try:
            with open(timeline_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug(f"Não foi possível escrever timeline: {e}")

    def get_timeline(self) -> list[dict[str, Any]]:
        """Retorna a timeline de eventos do job."""
        timeline_file = self.TIMELINE_DIR / f"{self.video_id}.jsonl"
        if not timeline_file.exists():
            return []

        events = []
        try:
            with open(timeline_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))
        except Exception as e:
            logger.error(f"Erro lendo timeline: {e}")

        return events

    def get_resume_info(self) -> dict[str, Any] | None:
        """
        Retorna info completa para resume.

        Returns dict com:
        - resume_from: próximo estágio
        - skip_stages: estágios já concluídos
        - state: estado atual
        - artifacts: artefatos disponíveis
        - timeline: eventos recentos
        """
        if not self.enabled or self._record is None:
            return None

        next_stage, skip = self._record.get_resume_point()
        return {
            "resume_from": next_stage.value if next_stage else None,
            "skip_stages": [s.value for s in skip],
            "state": self._record.state.value,
            "job_id": self._record.job_id,
            "artifacts": self._record.metadata.artifacts,
            "last_error": self._record.last_error,
            "retry_count": self._record.retry_count,
            "pipeline_version": self._record.metadata.pipeline_version,
        }


# ─── Instância global para uso fábrica ───

def get_job_manager(video_id: str) -> JobManager:
    """Factory para obter um JobManager configurado."""
    return JobManager(video_id=video_id)


def job_enabled() -> bool:
    """Verifica se o gerenciamento de estado está habilitado."""
    return os.getenv("FEATURE_PIPELINE_STATE", "false").lower() in ("true", "1", "yes")
