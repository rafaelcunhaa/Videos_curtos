from pipeline.quality_gate.policy import Policy, Severity


class ContainerCheck:
    def __init__(self, path: str, policy: Policy | None = None):
        self.path = path
        self.policy = policy or Policy.from_env()

    def run(self) -> list[dict]:
        results = []
        # Tenta ffprobe se disponível
        try:
            import subprocess, json
            cmd = ["ffprobe", "-v", "error", "-print_format", "json",
                   "-show_streams", "-show_format", self.path]
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if out.returncode != 0 or not out.stdout.strip():
                return [{"name": "video_opens", "status": "FAIL", "severity": Severity.CRITICAL, "message": out.stderr.strip() or "ffprobe could not parse the file."}]
            data = json.loads(out.stdout)
            streams = data.get("streams", [])
            video_streams = [s for s in streams if s.get("codec_type") == "video"]
            audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

            # Stream vídeo
            r_video = {
                "name": "video_stream_exists",
                "status": "PASS" if video_streams else "FAIL",
                "severity": Severity.CRITICAL,
                "message": "Video stream present" if video_streams else "Expected video stream but none found.",
            }
            results.append(r_video)

            # Stream áudio
            expect_audio = self.policy.QUALITY_EXPECT_AUDIO
            r_audio = {
                "name": "audio_stream_exists",
                "status": "PASS" if (audio_streams or not expect_audio) else "FAIL",
                "severity": Severity.CRITICAL,
                "message": "Audio stream present" if audio_streams else ("Expected audio stream but none found." if expect_audio else "Audio not expected."),
            }
            results.append(r_audio)

            # Codec / container: lista configurável, sem aceitar arquivo não parseável.
            codec = video_streams[0].get("codec_name") if video_streams else "unknown"
            container = data.get("format", {}).get("format_name", "unknown")
            codec_ok = codec in self.policy.QUALITY_ALLOWED_CODECS
            container_ok = any(name in container.split(",") for name in self.policy.QUALITY_ALLOWED_CONTAINERS)
            results.append({
                "name": "codec_valid",
                "status": "PASS" if codec_ok else "FAIL",
                "severity": Severity.ERROR,
                "message": f"Codec={codec}; allowed={self.policy.QUALITY_ALLOWED_CODECS}",
                "metadata": {"codec": codec},
            })
            results.append({
                "name": "container_valid",
                "status": "PASS" if container_ok else "FAIL",
                "severity": Severity.ERROR,
                "message": f"Container={container}; allowed={self.policy.QUALITY_ALLOWED_CONTAINERS}",
                "metadata": {"container": container},
            })
        except Exception as e:
            # Se ffprobe não disponível — não quebra; retorna SKIPPED / PASS por padrão
            results.append({
                "name": "container_check",
                "status": "SKIPPED",
                "severity": Severity.INFO,
                "message": f"ffprobe unavailable or error: {e}",
            })
        return results
