from dataclasses import dataclass
from typing import Optional


@dataclass
class SceneSpec:
    scene_id: str
    video_id: str
    start_time: float = 0.0
    duration: float = 5.0
    source: str = "gemini"
    prompt: str = ""
    theme: str = ""
    emotion: str = ""
    visual_style: str = "cinematic_realistic"
    aspect_ratio: str = "9:16"
    status: str = "pending"
    prompt_hash: Optional[str] = None
