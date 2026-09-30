from .models import SceneSpec
from typing import List

def plan_scenes(
    roteiro: str,
    duration_target: float = 35.0,
    theme: str = "",
    hook: str = "",
    impact_phrase: str = "",
    strategy: str = "mixed",
) -> List[SceneSpec]:
    # Isolado: não chama API. Usa heurística simples de roteiro.
    scenes = []
    # Hook sempre cena AI (opcional pelo usuário manualmente)
    scenes.append(SceneSpec(
        scene_id="scene_001", video_id="v1", start_time=0.0,
        duration=min(5.0, duration_target*0.15), source="gemini",
        purpose="HOOK", theme=theme, emotion="reflexao",
        visual_style="cinematic_realistic", prompt="Hook visual vertical 9:16, movimento imediato",
    ))
    # Desenvolvimento com stock
    scenes.append(SceneSpec(scene_id="scene_002", video_id="v1", start_time=5.0,
        duration=min(7.0, duration_target*0.2), source="stock", purpose="ESTABLISHING"))
    # Impacto com gemini se mixed
    if strategy in ("gemini", "mixed"):
        scenes.append(SceneSpec(scene_id="scene_003", video_id="v1", start_time=12.0,
            duration=min(5.0, duration_target*0.15), source="gemini", purpose="IMPACT"))
    # Ending stock
    scenes.append(SceneSpec(scene_id="scene_004", video_id="v1", start_time=17.0,
        duration=min(5.0, duration_target*0.15), source="stock", purpose="ENDING"))
    return scenes
