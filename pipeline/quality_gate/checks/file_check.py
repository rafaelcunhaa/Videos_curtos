from pipeline.quality_gate.policy import Policy, Severity


class FileCheck:
    def __init__(self, path: str, policy: Policy | None = None):
        self.path = path
        self.policy = policy or Policy.from_env()

    def run(self) -> list[dict]:
        import os
        result = {
            "name": "file_exists",
            "status": "PASS",
            "severity": Severity.CRITICAL,
            "message": "",
        }
        if not os.path.exists(self.path):
            result.update({"status": "FAIL", "message": f"File not found: {self.path}"})
            return [result]
        size = os.path.getsize(self.path)
        if size <= 0:
            result.update({"status": "FAIL", "message": "File size is 0 bytes"})
            return [result]
        ext = os.path.splitext(self.path)[1].lower()
        if ext not in self.policy.QUALITY_ALLOWED_EXTS:
            result.update({
                "status": "FAIL",
                "message": f"Invalid extension: {ext}; allowed={self.policy.QUALITY_ALLOWED_EXTS}",
                "severity": Severity.WARNING,
            })
        # Tenta abrir
        try:
            with open(self.path, "rb") as f:
                f.read(1)
        except Exception as e:
            result.update({"status": "FAIL", "message": f"Cannot open file: {e}"})
        return [result]
