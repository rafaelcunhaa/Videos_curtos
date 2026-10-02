"""Regressões mínimas para as garantias de hardening de segurança."""

from pathlib import Path
import inspect
import subprocess

from repositories.job_repository import JobRepository
from servidor import BASE_DIR, secure_path


ROOT = Path(__file__).resolve().parents[1]


def test_gitignore_protects_environment_and_credentials():
    rules = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in rules
    assert ".env.*" in rules
    assert "token.json" in rules
    assert "credentials.json" in rules
    assert "!.env.example" in rules


def test_sensitive_files_are_not_tracked():
    for filename in (".env", "token.json", "token_tiktok.json"):
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", filename],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0, f"arquivo sensível rastreado: {filename}"


def test_secure_path_rejects_path_traversal():
    try:
        secure_path("output", "..", "..", "secret.txt")
    except ValueError:
        return
    raise AssertionError("path traversal deveria ser rejeitado")


def test_secure_path_returns_path_inside_base_directory():
    path = secure_path("output", "secret.txt")
    base = BASE_DIR.resolve()

    assert path.resolve() == base / "output" / "secret.txt"
    assert base == path.resolve() or base in path.resolve().parents


def test_job_repository_uses_sql_parameters():
    source = inspect.getsource(JobRepository)

    assert "WHERE id = ?" in source
    assert "SET state = ?, updated_at = datetime('now') WHERE id = ?" in source
    assert "f\"" not in source
    assert "f'" not in source
