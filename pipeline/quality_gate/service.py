from pipeline.quality_gate.policy import Policy, Mode, Severity
from pipeline.quality_gate.checks.file_check import FileCheck
from pipeline.quality_gate.checks.container_check import ContainerCheck
from pipeline.quality_gate.checks.resolution_check import ResolutionCheck
from pipeline.quality_gate.checks.duration_check import DurationCheck
from pipeline.quality_gate.checks.audio_check import AudioCheck
from pipeline.quality_gate.checks.fps_check import FpsCheck
from pipeline.quality_gate.checks.safe_area_check import SafeAreaCheck
from pipeline.quality_gate.checks.silence_check import SilenceCheck
from pipeline.quality_gate.checks.black_frame_check import BlackFrameCheck
from pipeline.quality_gate.checks.captions_check import CaptionsCheck
from pipeline.quality_gate.checks.metadata_check import MetadataCheck
from pipeline.quality_gate.checks.assets_check import AssetsCheck
from pipeline.quality_gate.checks.thumbnail_check import ThumbnailCheck
from pipeline.quality_gate.checks.title_description_cta_check import TitleDescriptionCtaCheck
from pipeline.quality_gate.checks.visual_check import VisualCheck
from pipeline.quality_gate.cache import GateCache


class QualityGate:
    """Quality Gate — valida, classifica, reporta; NÃO corrige."""
    def __init__(self, video_path: str, metadata: dict = None,
                 manifest_path: str = "", caption_path: str = "",
                 thumb_path: str = "", policy: Policy = None):
        self.video_path = video_path
        self.metadata = metadata or {}
        self.manifest_path = manifest_path
        self.caption_path = caption_path
        self.thumb_path = thumb_path
        self.policy = policy or Policy.from_env()
        self.mode = Mode.from_env()
        self.results = []
        self.cache = GateCache()

    def run(self) -> dict:
        # Cache
        # Arquivos ausentes/vazios nunca usam cache e sempre são bloqueados.
        import os
        if not os.path.exists(self.video_path) or os.path.getsize(self.video_path) <= 0:
            result = {
                "status": "BLOCKED",
                "video_id": self.metadata.get("video_id", self.video_path),
                "checks": FileCheck(self.video_path, self.policy).run(),
                "errors": [], "warnings": [], "mode": self.mode.value,
            }
            result["errors"] = [c for c in result["checks"] if c.get("status") == "FAIL"]
            return result

        cached = self.cache.get(self.video_path)
        if cached is not None:
            return cached

        # Coleta checks
        all_checks = []
        all_checks.extend(FileCheck(self.video_path, self.policy).run())
        all_checks.extend(ContainerCheck(self.video_path, self.policy).run())
        all_checks.extend(ResolutionCheck(self.video_path, self.policy).run())
        all_checks.extend(DurationCheck(self.video_path, self.policy).run())
        all_checks.extend(AudioCheck(self.video_path, self.policy).run())
        all_checks.extend(FpsCheck(self.video_path, self.policy).run())
        all_checks.extend(SilenceCheck(self.video_path, self.policy).run())
        all_checks.extend(BlackFrameCheck(self.video_path, self.policy).run())
        all_checks.extend(SafeAreaCheck(self.metadata, self.policy).run())
        all_checks.extend(CaptionsCheck(self.video_path, self.policy, self.caption_path).run())
        all_checks.extend(MetadataCheck(self.video_path, self.metadata, self.manifest_path, self.policy).run())
        all_checks.extend(AssetsCheck(self.video_path, self.manifest_path, self.policy).run())
        all_checks.extend(ThumbnailCheck(self.video_path, self.policy, self.thumb_path).run())
        # Verificação visual mínima (não Remotion) — frames estratégicos via ffmpeg
        all_checks.extend(VisualCheck(self.video_path, self.policy).run())
        all_checks.extend(TitleDescriptionCtaCheck(self.metadata, self.policy).run())

        # Classifica: CRITICAL/ERROR bloqueiam; WARNING só bloqueia em strict.
        critical_failed = any(
            r.get("status") == "FAIL" and r.get("severity") in (Severity.CRITICAL, Severity.ERROR)
            for r in all_checks
        )
        warnings = [r for r in all_checks if r.get("status") == "FAIL" and r.get("severity") == Severity.WARNING]
        # Strict mode: alguns warnings também bloqueiam (simplificado)
        strict_block = False
        if self.mode == Mode.STRICT and warnings:
            strict_block = True

        if critical_failed or strict_block:
            status = "BLOCKED"
        elif warnings:
            status = "WARNING"
        else:
            status = "APPROVED"

        result = {
            "status": status,
            "video_id": self.metadata.get("video_id", self.video_path),
            "checks": all_checks,
            "errors": [r for r in all_checks if r.get("status") == "FAIL"],
            "warnings": [r for r in all_checks if r.get("status") == "FAIL" and r.get("severity") == Severity.WARNING],
            "mode": self.mode.value if hasattr(self.mode, "value") else str(self.mode),
        }
        self.cache.set(self.video_path, result)
        self.results = all_checks
        return result
