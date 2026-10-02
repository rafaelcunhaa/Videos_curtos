"""
Quality Gate — ETAPA 4 (Pré-publicação isolada, não corrige automaticamente)
"""
from .policy import Policy, Mode, Severity
from .report import GateReport
from .errors import GateError
from .cache import GateCache
from .checks.file_check import FileCheck
from .checks.container_check import ContainerCheck
from .checks.resolution_check import ResolutionCheck
from .checks.duration_check import DurationCheck
from .checks.audio_check import AudioCheck
from .checks.fps_check import FpsCheck
from .checks.captions_check import CaptionsCheck
from .checks.metadata_check import MetadataCheck
from .service import QualityGate
from .integration import run_quality_gate_for_job
from .checks.assets_check import AssetsCheck

__all__ = [
    "Policy", "Mode", "Severity", "GateReport", "GateError", "GateCache",
    "FileCheck", "ContainerCheck", "ResolutionCheck", "DurationCheck",
    "AudioCheck", "FpsCheck", "CaptionsCheck", "MetadataCheck", "AssetsCheck", "QualityGate", "run_quality_gate_for_job",
]
