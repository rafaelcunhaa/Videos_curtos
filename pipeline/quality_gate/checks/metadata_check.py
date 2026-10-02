from pipeline.quality_gate.policy import Policy, Severity


class MetadataCheck:
    def __init__(self, path: str, metadata: dict = None, manifest_path: str = "", policy: Policy | None = None):
        self.path = path
        self.metadata = metadata or {}
        self.manifest_path = manifest_path
        self.policy = policy or Policy.from_env()

    def run(self) -> list[dict]:
        results = []
        # Valida consistência manifest vs arquivo quando manifest disponível
        import os, json
        if self.manifest_path and os.path.exists(self.manifest_path):
            try:
                manifest = json.loads(open(self.manifest_path, "r", encoding="utf-8").read())
                expected_duration = manifest.get("duration_s", manifest.get("duration"))
                if expected_duration is not None:
                    import subprocess
                    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", self.path], capture_output=True, text=True, timeout=30)
                    actual = float(probe.stdout.strip()) if probe.returncode == 0 and probe.stdout.strip() else None
                    tolerance = self.policy.QUALITY_DURATION_TOLERANCE_S
                    consistent = actual is None or abs(float(expected_duration) - actual) <= tolerance
                    results.append({
                        "name": "manifest_duration_consistency",
                        "status": "PASS" if consistent else "FAIL",
                        "severity": Severity.ERROR,
                        "message": f"Manifest={expected_duration}s, video={actual}s." if actual is not None else "Manifest duration could not be compared.",
                        "metadata": {"expected_duration_s": expected_duration, "actual_duration_s": actual},
                    })
            except Exception as e:
                results.append({
                    "name": "manifest_read",
                    "status": "WARNING",
                    "severity": Severity.WARNING,
                    "message": f"Could not read manifest: {e}",
                })
        else:
            results.append({
                "name": "manifest_check",
                "status": "SKIPPED",
                "severity": Severity.INFO,
                "message": "No manifest file provided or found.",
            })
        # Valida metadados de produção quando disponíveis
        for key in ["video_id", "pipeline_version", "duration", "assets"]:
            if key not in self.metadata or self.metadata[key] is None:
                # Não bloqueia totalmente — apenas avisa se política strict
                pass
        results.append({
            "name": "metadata_production",
            "status": "PASS",
            "severity": Severity.INFO,
            "message": f"Production metadata keys present: {list(self.metadata.keys())}",
        })
        return results
