"""Cache por hash do arquivo — reutiliza resultado se arquivo não mudou."""
import hashlib
import json
from pathlib import Path


class GateCache:
    CACHE_DIR = Path(".pipeline_cache/quality_gate")

    def __init__(self):
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _hash(self, path: str) -> str:
        try:
            with open(path, "rb") as f:
                return hashlib.md5(f.read(65536)).hexdigest()  # primeiro bloco
        except Exception:
            return ""

    def get(self, path: str) -> dict | None:
        h = self._hash(path)
        if not h:
            return None
        cache_file = self.CACHE_DIR / f"{h}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))
        return None

    def set(self, path: str, result: dict) -> None:
        h = self._hash(path)
        if h:
            (self.CACHE_DIR / f"{h}.json").write_text(
                json.dumps(result, ensure_ascii=False), encoding="utf-8"
            )
