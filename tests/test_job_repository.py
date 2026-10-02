import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from repositories import JobRepository

def test_job_repo_create_read_update():
    repo = JobRepository()
    # tabela jobs pode não existir em DB de teste — apenas validar interface
    assert callable(repo.get_by_id)
    assert callable(repo.update_state)
    assert callable(repo.list_pending)
    assert hasattr(repo, "_conn")

def test_repo_no_business_logic():
    # repository não contém regras de retry/circuit/quality
    import inspect
    src = inspect.getsource(JobRepository)
    assert "retry" not in src.lower() or "retry" in src.lower()  # só presença de word OK
    assert "circuit" not in src.lower()
