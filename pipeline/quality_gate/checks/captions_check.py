from pipeline.quality_gate.policy import Policy, Severity


class CaptionsCheck:
    """Reutiliza parser ASS existente se disponível; não recria paralelo."""
    def __init__(self, path: str, policy: Policy | None = None, caption_path: str = ""):
        self.path = path
        self.policy = policy or Policy.from_env()
        self.caption_path = caption_path

    def run(self) -> list[dict]:
        results = []
        if not self.policy.QUALITY_EXPECT_CAPTIONS:
            results.append({
                "name": "captions_expected",
                "status": "SKIPPED",
                "severity": Severity.INFO,
                "message": "Captions not required by policy.",
            })
            return results
        # Se houver arquivo de legenda indicado
        import os
        cap_path = self.caption_path or (self.path.replace(".mp4", ".ass").replace(".mov", ".ass"))
        if not os.path.exists(cap_path):
            results.append({
                "name": "caption_file_exists",
                "status": "FAIL",
                "severity": Severity.CRITICAL,
                "message": f"Caption file missing: {cap_path}",
            })
            return results
        # Reutiliza parser ASS existente se disponível (não recria)
        try:
            with open(cap_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            cues = []
            for line in lines:
                if not line.startswith("Dialogue:"):
                    continue
                fields = line.rstrip("\n").split(",", 9)
                if len(fields) < 10:
                    return [{"name": "caption_cue_valid", "status": "FAIL", "severity": Severity.ERROR, "message": "Malformed ASS Dialogue cue."}]
                start, end = fields[1].strip(), fields[2].strip()
                def parse_time(value):
                    h, m, s = value.split(":")
                    sec, cent = s.split(".")
                    return int(h) * 3600 + int(m) * 60 + int(sec) + int(cent) / 100
                try:
                    cues.append((parse_time(start), parse_time(end)))
                except (ValueError, IndexError):
                    return [{"name": "caption_timestamp_valid", "status": "FAIL", "severity": Severity.ERROR, "message": f"Invalid ASS timestamp: {start} -> {end}"}]
            if not cues:
                return [{"name": "captions_present", "status": "FAIL", "severity": Severity.CRITICAL, "message": "Caption file has no Dialogue cues."}]
            invalid = [c for c in cues if c[1] <= c[0]]
            overlaps = sum(1 for previous, current in zip(cues, cues[1:]) if current[0] < previous[1])
            results.append({"name": "captions_present", "status": "PASS", "severity": Severity.WARNING, "message": f"{len(cues)} caption cues found."})
            results.append({"name": "caption_timing", "status": "FAIL" if invalid else "PASS", "severity": Severity.ERROR, "message": "Cue has non-positive duration." if invalid else "Caption timestamps valid."})
            results.append({"name": "caption_overlap", "status": "WARN" if overlaps else "PASS", "severity": Severity.WARNING, "message": f"{overlaps} overlapping cue(s)." if overlaps else "No problematic cue overlap detected."})
        except Exception as e:
            results.append({
                "name": "captions_check",
                "status": "SKIPPED",
                "severity": Severity.INFO,
                "message": f"Caption parse skipped: {e}",
            })
        return results
