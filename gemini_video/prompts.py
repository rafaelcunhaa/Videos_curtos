from .models import SceneSpec

def build_prompt(spec: SceneSpec) -> str:
    return (
        f"Video vertical 9:16, duração ~{spec.duration}s. "
        f"Tema: {spec.theme}; emoção: {spec.emotion}. "
        f"Estilo: {spec.visual_style}. "
        f"Movimento natural, composição para Shorts/TikTok, "
        f"espaço seguro para legendas, sem texto, sem logos, sem marcas d'água. "
        f"Cenário consistente com cenas anteriores."
    )
