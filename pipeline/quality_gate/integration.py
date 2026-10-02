"""Integração mínima e opt-in com JobManager.

O módulo de publicação não é alterado nesta etapa. Consumidores podem chamar
run_quality_gate_for_job antes de agendar/publicar.
"""
from typing import Any

from .service import QualityGate


def run_quality_gate_for_job(job_manager: Any, video_path: str, **kwargs: Any) -> dict:
    """Executa o gate e registra o resultado no JobManager quando habilitado."""
    result = QualityGate(video_path, **kwargs).run()
    job_manager.record_quality_gate(result)
    return result
