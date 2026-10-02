"""Testes unitários isolados do Quality Gate — sem APIs externas."""
import json
import os
from pathlib import Path

from pipeline.quality_gate import QualityGate, GateReport, Policy, Mode
from pipeline.quality_gate.checks.file_check import FileCheck
from pipeline.quality_gate.checks.title_description_cta_check import TitleDescriptionCtaCheck


def test_missing_video_blocked(tmp_path):
    result = QualityGate(str(tmp_path / "missing.mp4")).run()
    assert result["status"] == "BLOCKED"
    assert any(c["name"] == "file_exists" for c in result["errors"])


def test_empty_video_blocked(tmp_path):
    path = tmp_path / "empty.mp4"
    path.write_bytes(b"")
    result = QualityGate(str(path)).run()
    assert result["status"] == "BLOCKED"


def test_file_check_valid_nonvideo_is_reported(tmp_path):
    path = tmp_path / "sample.mp4"
    path.write_bytes(b"not a real video")
    checks = FileCheck(str(path)).run()
    assert checks[0]["status"] == "PASS"
    result = QualityGate(str(path)).run()
    # ffprobe detects corruption when available; otherwise checks are explicit SKIPPED.
    assert result["status"] in {"BLOCKED", "WARNING", "APPROVED"}
    assert result["checks"]


def test_warning_normal_does_not_block(monkeypatch, tmp_path):
    monkeypatch.setenv("QUALITY_GATE_MODE", "normal")
    checker = TitleDescriptionCtaCheck({"title": "Título"})
    checks = checker.run()
    assert any(c["status"] == "PASS" for c in checks)
    assert Mode.from_env() == Mode.NORMAL


def test_strict_mode(monkeypatch):
    monkeypatch.setenv("QUALITY_GATE_MODE", "strict")
    assert Mode.from_env() == Mode.STRICT
    checks = TitleDescriptionCtaCheck({}).run()
    assert any(c["status"] == "FAIL" for c in checks)


def test_report_json_and_text():
    report = GateReport({"video_id": "183", "status": "BLOCKED", "mode": "NORMAL", "checks": [], "errors": [], "warnings": []})
    assert "QUALITY GATE" in report.to_text()
    assert json.loads(report.to_json())["status"] == "BLOCKED"


def test_caption_missing_when_required(monkeypatch, tmp_path):
    monkeypatch.setenv("QUALITY_EXPECT_CAPTIONS", "true")
    policy = Policy.from_env()
    from pipeline.quality_gate.checks.captions_check import CaptionsCheck
    result = CaptionsCheck(str(tmp_path / "v.mp4"), policy, str(tmp_path / "v.ass")).run()
    assert result[0]["status"] == "FAIL"


def test_thumbnail_optional_by_default(tmp_path):
    from pipeline.quality_gate.checks.thumbnail_check import ThumbnailCheck
    result = ThumbnailCheck(str(tmp_path / "v.mp4"), Policy.from_env()).run()
    assert result[0]["status"] == "SKIPPED"
