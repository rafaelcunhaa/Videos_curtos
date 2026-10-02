"""Política centralizada — nenhuma regra espalhada pelo código."""
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class Mode(str, Enum):
    NORMAL = "NORMAL"
    STRICT = "STRICT"

    @classmethod
    def from_env(cls) -> "Mode":
        import os
        value = os.getenv("QUALITY_GATE_MODE", "normal").upper()
        return cls.STRICT if value == cls.STRICT.value else cls.NORMAL


class Policy:
    # Arquivo
    QUALITY_MIN_SIZE_BYTES: int = 1
    QUALITY_MAX_SIZE_BYTES: int = 10_000_000_000  # 10 GB
    QUALITY_ALLOWED_EXTS: list[str] = [".mp4", ".mov", ".mkv", ".avi"]

    # Container / codec (via ffprobe quando disponível)
    QUALITY_EXPECT_VIDEO_STREAM: bool = True
    QUALITY_EXPECT_AUDIO_STREAM: bool = True

    # Resolução / proporção
    QUALITY_ASPECT_RATIO: str = "9:16"
    QUALITY_ALLOWED_RESOLUTIONS: list[str] = ["1080x1920", "720x1280", "1080x1080"]

    # Duração
    QUALITY_MIN_DURATION_S: float = 10.0
    QUALITY_MAX_DURATION_S: float = 120.0
    QUALITY_DURATION_TOLERANCE_S: float = 1.5

    # FPS
    QUALITY_MIN_FPS: float = 10.0
    QUALITY_ALLOWED_CODECS: list[str] = ["h264", "hevc", "av1", "vp9"]
    QUALITY_ALLOWED_CONTAINERS: list[str] = ["mov,mp4,m4a,3gp,3g2,mj2", "matroska,webm"]
    QUALITY_AUDIO_DURATION_TOLERANCE_S: float = 1.5

    # Áudio
    QUALITY_EXPECT_AUDIO: bool = True
    QUALITY_AUDIO_MAX_SILENCE_RATIO: float = 0.95  # opcional, não bloqueia automático

    # Legendas
    QUALITY_EXPECT_CAPTIONS: bool = False

    # Thumbnail
    QUALITY_EXPECT_THUMBNAIL: bool = False

    # Safe Area / Metadata / Assets — políticas configuráveis, não hardcoded
    QUALITY_CHECK_SAFE_AREA: bool = False
    QUALITY_CHECK_METADATA: bool = True
    QUALITY_CHECK_ASSETS: bool = True

    @classmethod
    def from_env(cls) -> "Policy":
        import os
        p = cls()
        p.QUALITY_EXPECT_AUDIO = os.getenv("QUALITY_EXPECT_AUDIO", "true").lower() in ("true", "1", "yes")
        p.QUALITY_MIN_DURATION_S = float(os.getenv("QUALITY_MIN_DURATION_S", "10"))
        p.QUALITY_MAX_DURATION_S = float(os.getenv("QUALITY_MAX_DURATION_S", "120"))
        p.QUALITY_DURATION_TOLERANCE_S = float(os.getenv("QUALITY_DURATION_TOLERANCE_S", "1.5"))
        resolutions = os.getenv("QUALITY_ALLOWED_RESOLUTIONS", "1080x1920,720x1280,1080x1080")
        p.QUALITY_ALLOWED_RESOLUTIONS = [x.strip() for x in resolutions.split(",") if x.strip()]
        p.QUALITY_EXPECT_CAPTIONS = os.getenv("QUALITY_EXPECT_CAPTIONS", "false").lower() in ("true", "1", "yes")
        p.QUALITY_EXPECT_THUMBNAIL = os.getenv("QUALITY_EXPECT_THUMBNAIL", "false").lower() in ("true", "1", "yes")
        p.QUALITY_CHECK_SAFE_AREA = os.getenv("QUALITY_CHECK_SAFE_AREA", "false").lower() in ("true", "1", "yes")
        return p
