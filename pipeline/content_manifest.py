
"""Content Manifest � ETAPA 7. Registra COMO cada v�deo foi produzido."""
from typing import Any

class ContentManifest:
    """
    Manifest t�cnico por v�deo.
    Exemplos de campos: video_id, pipeline_version, script_version,
    visual_strategy, scenes[], voice, music, caption_style, title_version.
    """
    def __init__(self, video_id: str, pipeline_version: str = "2.0.0", job_id: str = None, schema_version: str = "1"):
        self.schema_version = schema_version
        self.video_id = video_id
        self.job_id = job_id
        self.pipeline_version = pipeline_version
        self.script_version = 1
        self.visual_version = 1
        self.scenes = []
        self.asset_versions = {}

    def add_scene(self, source: str, asset_id: str, version: int = 1):
        self.scenes.append({"source": source, "asset_id": asset_id, "version": version})

    @staticmethod
    def sha256(path: str) -> str:
        """Hash do artefato real; não usa nome de arquivo como identidade."""
        import hashlib
        digest = hashlib.sha256()
        with open(path, "rb") as artifact:
            for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def to_dict(self) -> dict[str, Any]:
        import hashlib, time
        return {
            "schema_version": self.schema_version,
            "video_id": self.video_id,
            "job_id": self.job_id,
            "pipeline_version": self.pipeline_version,
            "script_version": self.script_version,
            "visual_version": self.visual_version,
            "scenes": self.scenes,
            "asset_versions": self.asset_versions,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
