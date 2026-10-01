"""
Modelos de dados para Job State Management.

Define enums de estados/estágios e dataclasses para metadados de jobs.
Projetado para ser extensível por futuras etapas/providers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class JobState(str, Enum):
    """
    Estados principais do job (nível macro).

    Representam o estado geral do processamento do vídeo.
    """
    # Estados de progresso normal
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    SCRIPT_READY = "SCRIPT_READY"
    AUDIO_READY = "AUDIO_READY"
    MEDIA_READY = "MEDIA_READY"
    EDITING = "EDITING"
    VALIDATING = "VALIDATING"
    READY = "READY"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"

    # Estados de controle/erro
    FAILED = "FAILED"
    PAUSED = "PAUSED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"


class JobStage(str, Enum):
    """
    Estágios granulares do pipeline (nível micro).

    Cada estágio representa uma operação atômica que pode ser
    concluída independentemente e ter seu resultado cacheado.
    """
    # Planejamento
    PLANNING = "planning"
    SCRIPT_GENERATION = "script_generation"
    SCRIPT_VALIDATION = "script_validation"

    # Áudio
    TTS_GENERATION = "tts_generation"
    AUDIO_VALIDATION = "audio_validation"

    # Mídia
    STOCK_DOWNLOAD = "stock_download"
    GEMINI_IMPORT = "gemini_import"
    MEDIA_VALIDATION = "media_validation"

    # Montagem
    VIDEO_ASSEMBLY = "video_assembly"
    RENDER = "render"

    # Qualidade
    QUALITY_GATE = "quality_gate"
    VALIDATION = "validation"

    # Publicação
    SCHEDULING = "scheduling"
    YOUTUBE_UPLOAD = "youtube_upload"
    TIKTOK_UPLOAD = "tiktok_upload"
    PUBLICATION = "publication"


# Ordem canônica dos estágios para determinar progresso
STAGE_ORDER: list[JobStage] = [
    JobStage.PLANNING,
    JobStage.SCRIPT_GENERATION,
    JobStage.SCRIPT_VALIDATION,
    JobStage.TTS_GENERATION,
    JobStage.AUDIO_VALIDATION,
    JobStage.STOCK_DOWNLOAD,
    JobStage.GEMINI_IMPORT,
    JobStage.MEDIA_VALIDATION,
    JobStage.VIDEO_ASSEMBLY,
    JobStage.RENDER,
    JobStage.QUALITY_GATE,
    JobStage.VALIDATION,
    JobStage.SCHEDULING,
    JobStage.YOUTUBE_UPLOAD,
    JobStage.TIKTOK_UPLOAD,
    JobStage.PUBLICATION,
]

# Mapeamento de estágio para estado macro
STAGE_TO_STATE: dict[JobStage, JobState] = {
    JobStage.PLANNING: JobState.PLANNING,
    JobStage.SCRIPT_GENERATION: JobState.SCRIPT_READY,
    JobStage.SCRIPT_VALIDATION: JobState.SCRIPT_READY,
    JobStage.TTS_GENERATION: JobState.AUDIO_READY,
    JobStage.AUDIO_VALIDATION: JobState.AUDIO_READY,
    JobStage.STOCK_DOWNLOAD: JobState.MEDIA_READY,
    JobStage.GEMINI_IMPORT: JobState.MEDIA_READY,
    JobStage.MEDIA_VALIDATION: JobState.MEDIA_READY,
    JobStage.VIDEO_ASSEMBLY: JobState.EDITING,
    JobStage.RENDER: JobState.EDITING,
    JobStage.QUALITY_GATE: JobState.VALIDATING,
    JobStage.VALIDATION: JobState.VALIDATING,
    JobStage.SCHEDULING: JobState.SCHEDULED,
    JobStage.YOUTUBE_UPLOAD: JobState.PUBLISHED,
    JobStage.TIKTOK_UPLOAD: JobState.PUBLISHED,
    JobStage.PUBLICATION: JobState.PUBLISHED,
}

# Estados terminais (não podem progredir automaticamente)
TERMINAL_STATES: set[JobState] = {
    JobState.PUBLISHED,
    JobState.FAILED,
    JobState.CANCELLED,
}

# Estados que permitem retry
RETRYABLE_STATES: set[JobState] = {
    JobState.FAILED,
    JobState.PAUSED,
    JobState.RETRYING,
}

# Estados que indicam progresso ativo
ACTIVE_STATES: set[JobState] = {
    JobState.CREATED,
    JobState.PLANNING,
    JobState.SCRIPT_READY,
    JobState.AUDIO_READY,
    JobState.MEDIA_READY,
    JobState.EDITING,
    JobState.VALIDATING,
    JobState.READY,
    JobState.SCHEDULED,
    JobState.RETRYING,
}


@dataclass
class JobMetadata:
    """
    Metadados extensíveis do job.

    Campos customizados que diferentes providers/etapas podem usar.
    """
    # Identificação
    video_id: str = ""
    job_type: str = "shorts"
    pipeline_version: str = "1.0.0"

    # Provider específico (ex: "gemini_manual", "stock", "mixed")
    visual_strategy: str | None = None

    # Configurações usadas
    config_snapshot: dict[str, Any] = field(default_factory=dict)

    # Artefatos gerados (caminhos)
    artifacts: dict[str, str] = field(default_factory=dict)

    # Informações de provedor
    provider_info: dict[str, Any] = field(default_factory=dict)

    # Tags para busca/filtro
    tags: list[str] = field(default_factory=list)

    # Métricas de produção
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class JobRecord:
    """
    Registro completo de um job no banco de dados.

    Corresponde à tabela `pipeline_jobs`.
    """
    # Identificação
    video_id: str
    job_id: str

    # Estado
    state: JobState = JobState.CREATED

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Progresso
    completed_stages: list[str] = field(default_factory=list)
    stage_timestamps: dict[str, str] = field(default_factory=dict)

    # Erro
    last_error: str | None = None
    error_stage: str | None = None
    retry_count: int = 0
    next_retry_at: datetime | None = None

    # Metadados
    metadata: JobMetadata = field(default_factory=JobMetadata)

    # Controle
    is_active: bool = True

    def get_current_stage(self) -> JobStage | None:
        """Retorna o último estágio concluído ou o próximo a executar."""
        if not self.completed_stages:
            return STAGE_ORDER[0] if STAGE_ORDER else None

        last_completed = self.completed_stages[-1]
        try:
            idx = [s.value for s in STAGE_ORDER].index(last_completed)
            if idx + 1 < len(STAGE_ORDER):
                return STAGE_ORDER[idx + 1]
        except ValueError:
            pass
        return None

    def get_resume_point(self) -> tuple[JobStage | None, list[JobStage]]:
        """
        Retorna o ponto de resume e estágios a pular.

        Returns:
            (próximo_estágio_a_executar, estágios_para_pular)
        """
        skip = [JobStage(s) for s in self.completed_stages if s in [st.value for st in STAGE_ORDER]]
        next_stage = self.get_current_stage()
        return next_stage, skip

    def is_stage_completed(self, stage: JobStage) -> bool:
        """Verifica se um estágio já foi concluído (idempotência)."""
        return stage.value in self.completed_stages

    def mark_stage_completed(self, stage: JobStage, artifact_path: str | None = None) -> None:
        """Marca um estágio como concluído."""
        if stage.value not in self.completed_stages:
            self.completed_stages.append(stage.value)
            self.stage_timestamps[stage.value] = datetime.now().isoformat()

        if artifact_path:
            self.metadata.artifacts[stage.value] = artifact_path

        # Atualiza estado macro
        new_state = STAGE_TO_STATE.get(stage)
        if new_state and new_state not in TERMINAL_STATES:
            self.state = new_state

        self.updated_at = datetime.now()

    def mark_failed(self, stage: JobStage, error: str) -> None:
        """Marca o job como falho em um estágio."""
        self.state = JobState.FAILED
        self.last_error = error
        self.error_stage = stage.value
        self.retry_count += 1
        self.updated_at = datetime.now()

    def mark_paused(self, reason: str, next_retry_at: datetime | None = None) -> None:
        """Pausa o job."""
        self.state = JobState.PAUSED
        self.last_error = reason
        self.next_retry_at = next_retry_at
        self.updated_at = datetime.now()

    def mark_retrying(self) -> None:
        """Marca o job como em retry."""
        self.state = JobState.RETRYING
        self.updated_at = datetime.now()

    def mark_cancelled(self, reason: str) -> None:
        """Cancela o job."""
        self.state = JobState.CANCELLED
        self.last_error = reason
        self.is_active = False
        self.updated_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Converte para dict para persistência."""
        return {
            "video_id": self.video_id,
            "job_id": self.job_id,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_stages": self.completed_stages,
            "stage_timestamps": self.stage_timestamps,
            "last_error": self.last_error,
            "error_stage": self.error_stage,
            "retry_count": self.retry_count,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
            "metadata": {
                "video_id": self.metadata.video_id,
                "job_type": self.metadata.job_type,
                "pipeline_version": self.metadata.pipeline_version,
                "visual_strategy": self.metadata.visual_strategy,
                "config_snapshot": self.metadata.config_snapshot,
                "artifacts": self.metadata.artifacts,
                "provider_info": self.metadata.provider_info,
                "tags": self.metadata.tags,
                "metrics": self.metadata.metrics,
            },
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobRecord":
        """Cria JobRecord a partir de dict do banco."""
        meta_data = data.get("metadata", {})
        metadata = JobMetadata(
            video_id=meta_data.get("video_id", ""),
            job_type=meta_data.get("job_type", "shorts"),
            pipeline_version=meta_data.get("pipeline_version", "1.0.0"),
            visual_strategy=meta_data.get("visual_strategy"),
            config_snapshot=meta_data.get("config_snapshot", {}),
            artifacts=meta_data.get("artifacts", {}),
            provider_info=meta_data.get("provider_info", {}),
            tags=meta_data.get("tags", []),
            metrics=meta_data.get("metrics", {}),
        )

        return cls(
            video_id=data["video_id"],
            job_id=data["job_id"],
            state=JobState(data["state"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            completed_stages=data.get("completed_stages", []),
            stage_timestamps=data.get("stage_timestamps", {}),
            last_error=data.get("last_error"),
            error_stage=data.get("error_stage"),
            retry_count=data.get("retry_count", 0),
            next_retry_at=datetime.fromisoformat(data["next_retry_at"]) if data.get("next_retry_at") else None,
            metadata=metadata,
            is_active=data.get("is_active", True),
        )


def generate_job_id(video_id: str) -> str:
    """Gera ID único para o job."""
    import hashlib
    import time
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    hash_part = hashlib.md5(f"{video_id}{time.time()}".encode()).hexdigest()[:6]
    return f"{timestamp}-{hash_part}"