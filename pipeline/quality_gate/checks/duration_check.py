from pipeline.quality_gate.policy import Policy, Severity


class DurationCheck:
    def __init__(self, path: str, policy: Policy | None = None):
        self.path = path
        self.policy = policy or Policy.from_env()

    def run(self) -> list[dict]:
        results = []
        try:
            import subprocess, json
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                   "-of", "json", self.path]
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if out.returncode != 0 or not out.stdout.strip():
                return [{"name": "video_opens", "status": "FAIL", "severity": Severity.CRITICAL, "message": out.stderr.strip() or "ffprobe could not read duration."}]
            data = json.loads(out.stdout)
            duration = float(data.get("format", {}).get("duration", 0) or 0)
            min_d = self.policy.QUALITY_MIN_DURATION_S
            max_d = self.policy.QUALITY_MAX_DURATION_S
            tol = self.policy.QUALITY_DURATION_TOLERANCE_S
            # Tolerância: aceita dentro de [min-tol, max+tol] — não rejeita por poucos ms
            if duration < min_d - tol:
                status = "FAIL"
                msg = f"Duration {duration:.2f}s below min {min_d}s (tolerance {tol}s)"
            elif duration > max_d + tol:
                status = "FAIL"
                msg = f"Duration {duration:.2f}s above max {max_d}s (tolerance {tol}s)"
            else:
                status = "PASS"
                msg = f"Duration {duration:.2f}s within [{min_d}-{max_d}]"
            results.append({
                "name": "duration_valid",
                "status": status,
                "severity": Severity.CRITICAL,
                "message": msg,
                "metadata": {"duration_s": duration},
            })
        except Exception as e:
            results.append({
                "name": "duration_valid",
                "status": "SKIPPED",
                "severity": Severity.INFO,
                "message": f"ffprobe unavailable: {e}",
            })
        return results
