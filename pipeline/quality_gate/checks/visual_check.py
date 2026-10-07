"""Verificação visual básica de artifact de vídeo — não usa Remotion, apenas ffmpeg/ffprobe."""
from pathlib import Path
from pipeline.quality_gate.policy import Policy, Severity


class VisualCheck:
    """Verifica que frames estratégicos (início, meio, fim) podem ser extraídos do vídeo."""

    def __init__(self, path: str, policy: Policy | None = None, temp_dir: str = ".pipeline_cache/temp_frames"):
        self.path = path
        self.policy = policy or Policy.from_env()
        self.temp_dir = temp_dir

    # Emite eventos no AuditTrail existente (não cria mecanismo novo)
    def _audit_video_id(self) -> str:
        try:
            return Path(self.path).stem
        except Exception:
            return self.path

    def _emit_audit(self, event_name: str, status: str, msg: str = "", metadata: dict = None):
        try:
            from pipeline.observability.audit import AuditTrail
            from pipeline.observability.events import EventType
            from pipeline.observability.models import AuditEvent
            import time
            audit = AuditTrail()
            evt_map = {"start": EventType.VISUAL_VERIFY_STARTED.value,
                       "complete": EventType.VISUAL_VERIFY_COMPLETED.value,
                       "failed": EventType.VISUAL_VERIFY_FAILED.value}
            audit.record(AuditEvent(
                event_id=f"visual-verify-{self._audit_video_id()}-{time.strftime('%H%M%S')}",
                job_id=self._audit_video_id(),
                video_id=self.path,
                stage="visual_verify",
                event=evt_map.get(event_name, event_name),
                status=status,
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
                message=msg,
                metadata=metadata or {},
            ))
        except Exception:
            # Falha de auditoria não bloqueia a verificação visual
            pass

    def run(self) -> list[dict]:
        import os, subprocess, tempfile, json
        from pathlib import Path
        results = []
        # Se arquivo não existe, não tenta extrair — FileCheck já bloqueia.
        if not os.path.exists(self.path) or os.path.getsize(self.path) <= 0:
            return [{"name": "visual_check", "status": "SKIPPED", "severity": Severity.INFO,
                     "message": "Video file missing or empty; skipped frame extraction."}]

        # Determina duração via ffprobe (reutiliza padrão existente)
        duration = 0.0
        try:
            cmd_dur = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                       "-of", "json", self.path]
            out_dur = subprocess.run(cmd_dur, capture_output=True, text=True, timeout=30)
            if out_dur.returncode == 0 and out_dur.stdout.strip():
                duration = float(json.loads(out_dur.stdout).get("format", {}).get("duration", 0) or 0)
        except Exception as e:
            results.append({"name": "visual_check_duration", "status": "FAIL", "severity": Severity.WARNING,
                            "message": f"Could not read duration for frame selection: {e}"})

        # Pontos de verificação: início (~10%), meio (~50%), fim (~95%)
        frames_to_check = []
        if duration > 0:
            frames_to_check = [
                ("start", max(0.0, duration * 0.05)),
                ("mid", duration * 0.50),
                ("end", max(duration * 0.05, duration * 0.95)),
            ]
        else:
            # Se não conseguiu ler duração, tenta apenas início (1s) como fallback
            frames_to_check = [("start", 1.0)]

        tmp_path = Path(self.temp_dir)
        tmp_path.mkdir(parents=True, exist_ok=True)
        frames_extracted = 0
        errors = []
        # Emite start antes da extração de frames (registro no AuditTrail)
        self._emit_audit("start", "running", msg=f"Visual verification started for {self.path}", metadata={"video_id": self._audit_video_id(), "duration_s": duration})
        for label, timestamp in frames_to_check:
            output_path = tmp_path / f"{Path(self.path).stem}_frame_{label}.png"
            try:
                cmd = [
                    "ffmpeg", "-y", "-ss", str(timestamp),
                    "-i", self.path,
                    "-vframes", "1",
                    "-q:v", "2",
                    str(output_path),
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                    frames_extracted += 1
                else:
                    errors.append(f"Frame '{label}' at {timestamp:.2f}s failed: {res.stderr[-200:] if res.stderr else 'no output'}")
            except Exception as e:
                errors.append(f"Frame '{label}' exception: {e}")

        # Cleanup dos temporários (não deixa imagens acumularem)
        for output_path in tmp_path.glob(f"{Path(self.path).stem}_frame_*.png"):
            try:
                output_path.unlink()
            except Exception:
                pass

        if errors:
            self._emit_audit("failed", "failed", msg="; ".join(errors), metadata={"frames_extracted": frames_extracted, "duration_s": duration, "errors": errors})
            results.append({"name": "visual_check_frames", "status": "FAIL", "severity": Severity.ERROR,
                            "message": "; ".join(errors)})
        else:
            self._emit_audit("complete", "success", msg=f"Verified {frames_extracted} frames", metadata={"frames_checked": frames_extracted, "duration_s": duration})
            results.append({"name": "visual_check_frames", "status": "PASS", "severity": Severity.WARNING,
                            "message": f"Extracted and verified {frames_extracted} strategic frames (start/mid/end) from video.",
                            "metadata": {"frames_checked": frames_extracted, "duration_s": duration}})
        return results
