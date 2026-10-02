"""Relatório legível + JSON — não corrige, apenas reporta."""
import json
from pathlib import Path


class GateReport:
    def __init__(self, result: dict):
        self.result = result

    def to_text(self) -> str:
        lines = [
            "QUALITY GATE",
            "============",
            f"Video: {self.result.get('video_id', 'unknown')}",
            f"Status: {self.result.get('status', 'UNKNOWN')}",
            f"Mode: {self.result.get('mode', 'NORMAL')}",
            "",
            "PASS",
        ]
        for c in self.result.get("checks", []):
            if c.get("status") == "PASS":
                lines.append(f"✅ {c['name']}")
        lines.append("")
        lines.append("WARNING")
        for c in self.result.get("checks", []):
            if c.get("status") in ("FAIL", "WARN") and c.get("severity") == "WARNING":
                lines.append(f"⚠ {c['name']}: {c.get('message', '')}")
        lines.append("")
        lines.append("FAIL")
        for c in self.result.get("checks", []):
            if c.get("status") == "FAIL" and c.get("severity") in ("CRITICAL", "ERROR"):
                lines.append(f"❌ {c['name']}: {c.get('message', '')}")
        # Reason
        lines.append("")
        if self.result.get("status") == "BLOCKED":
            lines.append("Reason: Critical check(s) failed — publication blocked.")
        elif self.result.get("status") == "WARNING":
            lines.append("Reason: Non-critical warnings present — publication allowed with alert.")
        else:
            lines.append("Reason: All critical checks passed.")
        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps(self.result, ensure_ascii=False, indent=2)

    def save(self, path: str = "quality_gate_report.json") -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")
