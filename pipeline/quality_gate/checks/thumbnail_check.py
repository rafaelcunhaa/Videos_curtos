from pipeline.quality_gate.policy import Policy, Severity


class ThumbnailCheck:
    def __init__(self, video_path: str, policy: Policy | None = None, thumb_path: str = ""):
        self.video_path = video_path
        self.policy = policy or Policy.from_env()
        self.thumb_path = thumb_path or video_path.replace(".mp4", ".jpg").replace(".mov", ".jpg")

    def run(self) -> list[dict]:
        results = []
        if not self.policy.QUALITY_EXPECT_THUMBNAIL:
            results.append({
                "name": "thumbnail_check",
                "status": "SKIPPED",
                "severity": Severity.INFO,
                "message": "Thumbnail not required by policy.",
            })
            return results
        import os
        if not os.path.exists(self.thumb_path):
            results.append({
                "name": "thumbnail_exists",
                "status": "FAIL",
                "severity": Severity.CRITICAL,
                "message": f"Thumbnail missing: {self.thumb_path}",
            })
        else:
            # Abre para confirmar não corrompido
            try:
                with open(self.thumb_path, "rb") as f:
                    header = f.read(10)
                results.append({
                    "name": "thumbnail_exists",
                    "status": "PASS",
                    "severity": Severity.CRITICAL,
                    "message": f"Thumbnail {self.thumb_path} opens correctly.",
                    "metadata": {"header_bytes": header[:4].decode("ascii", errors="ignore")},
                })
            except Exception as e:
                results.append({
                    "name": "thumbnail_exists",
                    "status": "FAIL",
                    "severity": Severity.CRITICAL,
                    "message": f"Thumbnail corrupt: {e}",
                })
        return results
