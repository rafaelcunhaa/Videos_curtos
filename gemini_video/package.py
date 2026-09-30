import json
from pathlib import Path
from .planner import plan_scenes
from .prompts import build_prompt
from .models import SceneSpec

class ProductionPackage:
    def __init__(self, video_id: str, base: Path = Path("gemini_video/project")):
        self.base = base / video_id
        self.base.mkdir(parents=True, exist_ok=True)
        self.manifest = {"video_id": video_id, "scenes": []}

    def build(self, roteiro: str, duration: float = 35.0, strategy: str = "mixed"):
        scenes = plan_scenes(roteiro, duration, strategy=strategy)
        for s in scenes:
            s.prompt = build_prompt(s)
            self.manifest["scenes"].append({
                "scene_id": s.scene_id, "source": s.source,
                "purpose": s.purpose, "duration": s.duration,
                "prompt_file": f"prompts/{s.scene_id}.txt",
                "status": "pending"
            })
            (self.base / "prompts").mkdir(exist_ok=True)
            (self.base / "prompts" / f"{s.scene_id}.txt").write_text(s.prompt)
        (self.base / "Manifest.json").write_text(json.dumps(self.manifest, indent=2), encoding="utf-8")
        (self.base / "README.md").write_text("GEMINI PACK\n\nAbra Gemini/Flow.\nGere cenas.\nColoque MP4 em output/\nExecute importador.")
        return self.base
