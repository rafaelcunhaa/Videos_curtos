import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Round-trip backup/restore/reconciliation com tmp_path; nenhum dado real tocado."""
import tempfile, sqlite3
from pathlib import Path
from pipeline.backup_service import BackupService

def test_backup_and_restore_roundtrip(tmp_path):
    svc = BackupService(str(tmp_path))
    meta = svc.backup(str(tmp_path / "back"), dry_run=False)
    assert meta["status"] == "complete"
    assert meta["database"] is not None
    # restore sem confirm deve falhar
    try:
        svc.restore(str(tmp_path / "back"), confirm=False)
        assert False, "deveria exigir confirm"
    except PermissionError:
        pass
    # restore com confirm (dry-run primeiro)
    dry = svc.restore(str(tmp_path / "back"), confirm=True, dry_run=True)
    assert dry["status"] == "dry-run"

def test_reconcile_detects_issues(tmp_path):
    svc = BackupService(str(tmp_path))
    # criar db temporário mínimo
    db = tmp_path / "banco_shorts.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY, state TEXT)")
    conn.execute("INSERT INTO jobs (state) VALUES ('running')")
    conn.commit(); conn.close()
    issues = svc.reconcile()
    assert any(i["type"] == "job_running_check" for i in issues)
