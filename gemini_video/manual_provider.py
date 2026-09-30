from .provider import SceneProvider
from .models import SceneSpec
from pathlib import Path

class GeminiManualProvider:
    def generate(self, spec: SceneSpec) -> Path | None:
        # Não gera; apenas aponta para arquivo já importado pelo usuário
        path = Path("gemini_video/project") / spec.video_id / "output" / f"{spec.scene_id}.mp4"
        return path if path.exists() else None
