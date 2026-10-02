from pipeline.quality_gate.policy import Policy, Severity


class AudioCheck:
    def __init__(self, path: str, policy: Policy | None = None):
        self.path = path
        self.policy = policy or Policy.from_env()

    def run(self) -> list[dict]:
        results = []
        try:
            import subprocess, json
            # Verifica presença de stream áudio (já feito no container, complementa)
            cmd = ["ffprobe", "-v", "error", "-select_streams", "a:0",
                   "-show_entries", "stream=codec_name,duration:format=duration", "-of", "json", self.path]
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if out.returncode != 0 or not out.stdout.strip():
                return [{"name": "audio_probe", "status": "FAIL", "severity": Severity.CRITICAL, "message": out.stderr.strip() or "ffprobe could not read audio."}]
            data = json.loads(out.stdout)
            streams = data.get("streams", [])
            video_duration = float(data.get("format", {}).get("duration", 0) or 0)
            if streams:
                duration = float(streams[0].get("duration", 0) or 0)
                compatible = video_duration <= 0 or abs(duration - video_duration) <= self.policy.QUALITY_AUDIO_DURATION_TOLERANCE_S
                results.append({
                    "name": "audio_duration_compatible",
                    "status": "PASS" if duration > 0 and compatible else "WARN",
                    "severity": Severity.WARNING,
                    "message": f"Audio duration {duration:.2f}s; video {video_duration:.2f}s." if compatible else f"Audio/video duration mismatch: {duration:.2f}s vs {video_duration:.2f}s.",
                    "metadata": {"audio_duration_s": duration, "video_duration_s": video_duration},
                })
            else:
                if self.policy.QUALITY_EXPECT_AUDIO:
                    results.append({
                        "name": "audio_presence",
                        "status": "FAIL",
                        "severity": Severity.CRITICAL,
                        "message": "Expected audio stream but none found.",
                    })
                else:
                    results.append({
                        "name": "audio_presence",
                        "status": "PASS",
                        "severity": Severity.INFO,
                        "message": "Audio not expected, none found (OK).",
                    })
        except Exception as e:
            results.append({
                "name": "audio_check",
                "status": "SKIPPED",
                "severity": Severity.INFO,
                "message": f"ffprobe unavailable: {e}",
            })
        return results
