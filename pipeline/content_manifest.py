
"""Content Manifest — ETAPA 7. Registra COMO cada vídeo foi produzido."""
from typing import Any

class ContentManifest:
    """
    Manifest técnico por vídeo.
    Exemplos de campos: video_id, pipeline_version, script_version,
    visual_strategy, scenes[], voice, music, caption_style, title_version.
    """
    def __init__(self, video_id: str, pipeline_version: str = "2.0.0"):
        self.video_id = video_id
        self.pipeline_version = pipeline_version
        self.script_version = 1
        self.visual_version = 1
        self.scenes = []
        self.asset_versions = {}

    def add_scene(self, source: str, asset_id: str, version: int = 1):
        self.scenes.append({"source": source, "asset_id": asset_id, "version": version})

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_id": self.video_id,
            "pipeline_version": self.pipeline_version,
            "script_version": self.script_version,
            "visual_version": self.visual_version,
            "scenes": self.scenes,
            "asset_versions": self.asset_versions,
        }
