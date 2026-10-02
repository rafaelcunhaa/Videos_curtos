from pipeline.quality_gate.policy import Policy, Severity


class FpsCheck:
    def __init__(self, path: str, policy: Policy | None = None):
        self.path = path
        self.policy = policy or Policy.from_env()

    def run(self) -> list[dict]:
        import json
        import subprocess
        try:
            out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=avg_frame_rate", "-of", "json", self.path], capture_output=True, text=True, timeout=30)
            data = json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip() else {}
            value = data.get("streams", [{}])[0].get("avg_frame_rate", "0/0")
            numerator, denominator = value.split("/", 1)
            fps = float(numerator) / float(denominator)
            return [{"name": "fps_valid", "status": "PASS" if fps >= self.policy.QUALITY_MIN_FPS else "FAIL", "severity": Severity.ERROR, "message": f"FPS={fps:.3f}; minimum={self.policy.QUALITY_MIN_FPS}", "metadata": {"fps": fps}}]
        except Exception as e:
            return [{"name": "fps_valid", "status": "FAIL", "severity": Severity.ERROR, "message": f"Could not read FPS: {e}"}]
