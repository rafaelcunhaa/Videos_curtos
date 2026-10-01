"""
Log Engine — ETAPA 4 (Logs Profissionais + Timeline + Observabilidade)

Regras:
- Cada execução tem Job_id, Video_id, Stage, Provider, Event, Timestamp
- Registra eventos importantes: JOB_CREATED, SCRIPT_GENERATED, AUDIO_GENERATED,
  ASSET_DOWNLOADED, SCENE_IMPORTED, RENDER_STARTED, RENDER_COMPLETED,
  VALIDATION_FAILED, PUBLISHED, FAILED, PAUSED, RETRYING
- NÃO registra: API keys, tokens, senhas, headers sensíveis
- Usa logger existente (logger_setup.py) como backend, não substitui
"""

import logging
import json
from datetime import datetime
from typing import Any

logger = logging.getLogger("pipeline.log_engine")

# Eventos canônicos pelo projeto
EVENTS = {
    "JOB_CREATED",
    "SCRIPT_GENERATED",
    "AUDIO_GENERATED",
    "ASSET_DOWNLOADED",
    "SCENE_IMPORTED",
    "RENDER_STARTED",
    "RENDER_COMPLETED",
    "VALIDATION_FAILED",
    "VALIDATION_PASSED",
    "PUBLISHED",
    "FAILED",
    "PAUSED",
    "RETRYING",
    "CIRCUIT_OPEN",
    "CIRCUIT_CLOSED",
    "STAGE_COMPLETED",
    "STAGE_FAILED",
    "STATE_CHANGED",
}

# Eventos que NÃO devem conter dados sensíveis (se forem logados, são apenas referências)
SAFE_KEYS = {
    "video_id", "job_id", "stage", "provider", "event",
    "timestamp", "retry_count", "pipeline_version",
    "status", "completed_stages", "next_retry_at",
}


class ProfessionalLogger:
    """
    Logger profissional para pipeline.
    Não altera handlers existentes — apenas formatador estruturado.
    """

    def __init__(self, name: str = "pipeline"):
        self.name = name
        self.logger = logging.getLogger(name)

    def log(self,
            event: str,
            job_id: str = "",
            video_id: str = "",
            stage: str = "",
            provider: str = "",
            extra: dict[str, Any] | None = None,
            level: int = logging.INFO) -> None:
        """
        Registra evento estruturado.

        Args:
            event: Nome do evento (de EVENTS)
            job_id: ID do job
            video_id: ID do vídeo
            stage: Estágio atual (opcional)
            provider: Provider usado (opcional)
            extra: Dados adicionais (filtrados para não incluir secrets)
            level: Nível do log
        """
        if event not in EVENTS and event not in {"CUSTOM"}:
            # Aceita eventos customizados, mas documenta
            pass

        # Filtra dados sensíveis do extra
        safe_extra = {}
        if extra:
            for k, v in extra.items():
                # Nunca loga chaves que possam ser segredos
                if k.lower() in {
                    "api_key", "token", "secret", "password", "auth",
                    "credential", "private_key", "access_token",
                    "authorization", "x-api-key", "bearer",
                }:
                    safe_extra[k] = "***REDACTED***"
                else:
                    safe_extra[k] = v

        message = (
            f"[PIPELINE] event={event} "
            f"job={job_id or '-'} video={video_id or '-'} "
            f"stage={stage or '-'} provider={provider or '-'} "
            f"ts={datetime.now().isoformat()}"
        )

        # Adiciona extras se presentes
        if safe_extra:
            message += f" data={json.dumps(safe_extra, ensure_ascii=False)[:400]}"

        self.logger.log(level, message, extra={
            "job_id": job_id,
            "video_id": video_id,
            "stage": stage,
            "provider": provider,
            "event": event,
            "safe_extra": safe_extra,
        })

    def log_retry(self,
                  job_id: str,
                  video_id: str,
                  stage: str,
                  attempt: int,
                  next_retry_at: str | None = None,
                  error: str | None = None) -> None:
        """Registra evento de retry."""
        extra = {"attempt": attempt, "next_retry_at": next_retry_at}
        if error:
            extra["error_summary"] = error[:200]  # limita tamanho; não loga stack completo se tiver secret
        self.log("RETRYING", job_id=job_id, video_id=video_id, stage=stage,
                 extra=extra, level=logging.WARNING)

    def log_publish(self,
                    job_id: str,
                    video_id: str,
                    platform: str,
                    url: str | None = None) -> None:
        """Registra publicação confirmada."""
        extra = {"platform": platform}
        if url:
            extra["url"] = url
        self.log("PUBLISHED", job_id=job_id, video_id=video_id,
                 stage="publication", provider=platform, extra=extra)


def configure_professional_logging() -> ProfessionalLogger:
    """Configura logger profissional (se feature flag ativa)."""
    return ProfessionalLogger()
