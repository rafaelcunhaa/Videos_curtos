from pipeline.quality_gate.policy import Policy, Severity


class SilenceCheck:
    """Detecção opcional e conservadora; não bloqueia por silêncio narrativo legítimo."""
    def __init__(self, path: str, policy: Policy | None = None):
        self.path = path
        self.policy = policy or Policy.from_env()

    def run(self) -> list[dict]:
        return [{"name": "silence_analysis", "status": "SKIPPED", "severity": Severity.INFO, "message": "Optional silence analysis disabled; no automatic correction or blocking."}]
