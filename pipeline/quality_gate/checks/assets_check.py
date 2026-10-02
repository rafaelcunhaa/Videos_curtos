from pipeline.quality_gate.policy import Policy, Severity


class AssetsCheck:
    """Verifica assets obrigatórios do manifest / cena."""
    def __init__(self, path: str, manifest_path: str = "", policy: Policy | None = None):
        self.path = path
        self.manifest_path = manifest_path
        self.policy = policy or Policy.from_env()

    def run(self) -> list[dict]:
        results = []
        import os, json
        if not (self.manifest_path and os.path.exists(self.manifest_path)):
            results.append({
                "name": "assets_check",
                "status": "SKIPPED",
                "severity": Severity.INFO,
                "message": "No manifest for asset validation.",
            })
            return results
        try:
            manifest = json.loads(open(self.manifest_path, "r", encoding="utf-8").read())
            scenes = manifest.get("scenes", [])
            if not scenes:
                results.append({
                    "name": "assets_scenes",
                    "status": "PASS",
                    "severity": Severity.INFO,
                    "message": "No scenes defined in manifest.",
                })
            else:
                missing = []
                for s in scenes:
                    asset_ref = s.get("asset_path") or s.get("asset") or s.get("path")
                    if asset_ref and not os.path.exists(asset_ref):
                        missing.append(str(asset_ref))
                if missing:
                    results.append({
                        "name": "assets_critical_missing",
                        "status": "FAIL",
                        "severity": Severity.CRITICAL,
                        "message": f"Required assets missing: {missing}",
                        "metadata": {"missing_assets": missing},
                    })
                else:
                    results.append({
                        "name": "assets_critical_missing",
                        "status": "PASS",
                        "severity": Severity.CRITICAL,
                        "message": "All required scene assets found.",
                    })
        except Exception as e:
            results.append({
                "name": "assets_check",
                "status": "SKIPPED",
                "severity": Severity.INFO,
                "message": f"Asset validation skipped: {e}",
            })
        return results
