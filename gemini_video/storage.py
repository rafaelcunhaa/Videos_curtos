from pathlib import Path
from .models import SceneSpec

class SceneStorage:
    def __init__(self, base: Path = Path("gemini_video/data/outputs")):
        self.base = base
        self.base.mkdir(parents=True, exist_ok=True)

    def path_for(self, spec: SceneSpec) -> Path:
        return self.base / f"video_{spec.video_id}_scene_{spec.scene_id}_gemini.mp4"
