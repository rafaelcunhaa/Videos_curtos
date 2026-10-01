"""
Pipeline Package — Estado de Jobs, Resume e Idempotência

Este pacote fornece infraestrutura para gerenciar o ciclo de vida de jobs
do pipeline de automação de vídeos de forma persistente e recuperável.
"""

from .job_models import JobState, JobStage, JobMetadata
from .job_manager import JobManager

__all__ = [
    "JobState",
    "JobStage",
    "JobMetadata",
    "JobManager",
]