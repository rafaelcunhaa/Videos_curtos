"""Backup / Restore / Reconciliation — mínimo funcional.
- SQLite .backup; meta JSON (hash apenas críticos); restore exige confirm; dry_run.
- Nenhum secret; nenhum destructive automático.
"""
from __future__ import annotations
import hashlib, json, sqlite3, shutil, tempfile
from pathlib import Path


class BackupService:
    def __init__(self, base_dir: str = "."):
        self.base = Path(base_dir).resolve()

    @staticmethod
    def _sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def backup(self, target_dir: str, dry_run: bool = False) -> dict:
        t = Path(target_dir).resolve()
        db_path = self.base / "banco_shorts.db"
        meta = {
            "status": "dry-run" if dry_run else "complete",
            "database": str(db_path) if db_path.exists() else None,
            "hashes": {},
        }
        if dry_run:
            return meta
        t.mkdir(parents=True, exist_ok=True)
        if db_path.exists():
            backup_db = t / "banco_shorts.db"
            with sqlite3.connect(str(db_path)) as src:
                with sqlite3.connect(str(backup_db)) as dst:
                    src.backup(dst)
            meta["database"] = str(backup_db)
        # hashes apenas para arquivos críticos (manifests, repos), NÃO vídeos
        critical = [
            self.base / "pipeline/content_manifest.py",
            self.base / "repositories/job_repository.py",
            self.base / "repositories/publication_repository.py",
            self.base / "pipeline/quality_gate.py",
        ]
        for p in critical:
            if p.exists():
                meta["hashes"][str(p.name)] = self._sha256_file(p)
        meta_path = t / "backup_meta.json"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return meta

    def restore(self, source_dir: str, confirm: bool = False, dry_run: bool = False) -> dict:
        src = Path(source_dir).resolve()
        if not confirm:
            raise PermissionError("restore requer confirm=True")
        meta_path = src / "backup_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        if dry_run:
            return {"status": "dry-run", "meta": meta}
        db_src = src / "banco_shorts.db"
        db_dst = self.base / "banco_shorts.db"
        if db_src.exists():
            shutil.copy2(str(db_src), str(db_dst))
        return {"status": "restored", "meta": meta}

    def reconcile(self, db_path: str = "banco_shorts.db") -> list[dict]:
        issues = []
        db = self.base / db_path
        if db.exists():
            with sqlite3.connect(str(db)) as conn:
                cur = conn.execute("SELECT state FROM jobs WHERE state = 'running'")
                for row in cur.fetchall():
                    issues.append({"type": "job_running_check", "state": row[0]})
        return issues
