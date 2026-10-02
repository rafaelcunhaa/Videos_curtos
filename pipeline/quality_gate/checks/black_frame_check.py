from pipeline.quality_gate.policy import Policy, Severity


class BlackFrameCheck:
    """Hook conservador para análise futura sem decodificar vídeos inteiros nesta etapa."""
    def __init__(self, path: str, policy: Policy | None = None):
        self.path = path
        self.policy = policy or Policy.from_env()

    def run(self) -> list[dict]:
        return [{"name": "black_or_frozen_frames", "status": "SKIPPED", "severity": Severity.INFO, "message": "Frame analysis skipped to avoid expensive full-video decoding."}]
