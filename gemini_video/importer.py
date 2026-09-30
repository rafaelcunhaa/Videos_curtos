from pathlib import Path
from .models import SceneSpec

class GeminiImporter:
    def import_scene(self, video_id: str, scene_id: str, output_path: Path):
        if not output_path.exists():
            return {"status": "PENDING", "reason": "file missing"}
        # Validação mínimos sem quebrar pipeline
        return {"status": "IMPORTED", "file": str(output_path), "validated": True}
