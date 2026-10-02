from pipeline.quality_gate.policy import Policy, Severity


class SafeAreaCheck:
    """Valida dados determinísticos de safe area quando fornecidos."""
    def __init__(self, metadata: dict | None = None, policy: Policy | None = None):
        self.metadata = metadata or {}
        self.policy = policy or Policy.from_env()

    def run(self) -> list[dict]:
        if not self.policy.QUALITY_CHECK_SAFE_AREA:
            return [{"name": "safe_area", "status": "SKIPPED", "severity": Severity.INFO, "message": "Safe-area policy disabled."}]
        boxes = self.metadata.get("text_boxes")
        if not boxes:
            return [{"name": "safe_area", "status": "WARN", "severity": Severity.WARNING, "message": "Insufficient positioning data for automatic safe-area validation."}]
        invalid = [b for b in boxes if b.get("x", 0) < 0 or b.get("y", 0) < 0 or b.get("x2", 1) > 1 or b.get("y2", 1) > 1]
        return [{"name": "safe_area", "status": "FAIL" if invalid else "PASS", "severity": Severity.WARNING, "message": "Text outside normalized frame." if invalid else "Text boxes inside normalized frame."}]
