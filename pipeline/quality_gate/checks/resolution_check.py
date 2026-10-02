from pipeline.quality_gate.policy import Policy, Severity


class ResolutionCheck:
    def __init__(self, path: str, policy: Policy | None = None):
        self.path = path
        self.policy = policy or Policy.from_env()

    def run(self) -> list[dict]:
        results = []
        try:
            import subprocess, json
            cmd = ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
                   "-show_entries", "stream=width,height", "-of", "json", self.path]
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            data = json.loads(out.stdout) if out.returncode == 0 else {}
            stream = data.get("streams", [{}])[0]
            w = stream.get("width", 0) or 0
            h = stream.get("height", 0) or 0
            if w > 0 and h > 0:
                ratio_str = f"{w}x{h}"
                aspect = self.policy.QUALITY_ASPECT_RATIO  # ex: 9:16
                try:
                    ar_w, ar_h = (float(x) for x in aspect.split(":", 1))
                    expected_ratio = ar_w / ar_h
                    actual_ratio = w / h
                    aspect_ok = abs(actual_ratio - expected_ratio) <= 0.02
                except (ValueError, ZeroDivisionError):
                    aspect_ok = True
                allowed = self.policy.QUALITY_ALLOWED_RESOLUTIONS
                # A lista controla tamanhos; a proporção controla orientação/formato.
                ok_res = ratio_str in allowed and aspect_ok
                results.append({
                    "name": "resolution_ok",
                    "status": "PASS" if ok_res else "FAIL",
                    "severity": Severity.ERROR,
                    "message": f"Resolution {ratio_str}, aspect {aspect}; allowed={allowed}" if not ok_res else f"Resolution {ratio_str} OK",
                    "metadata": {"width": w, "height": h, "aspect_ratio": f"{w}:{h}"},
                })
            else:
                results.append({
                    "name": "resolution_ok",
                    "status": "FAIL",
                    "severity": Severity.ERROR,
                    "message": "Could not read resolution via ffprobe.",
                })
        except Exception as e:
            results.append({
                "name": "resolution_ok",
                "status": "SKIPPED",
                "severity": Severity.INFO,
                "message": f"ffprobe unavailable: {e}",
            })
        return results
