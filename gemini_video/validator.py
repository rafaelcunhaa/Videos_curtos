import hashlib
from pathlib import Path

class SceneValidator:
    def validate(self, path: Path) -> dict:
        if not path.exists():
            return {"valid": False, "reason": "missing"}
        h = hashlib.md5(path.read_bytes()).hexdigest()[:8]
        return {"valid": True, "hash": h, "path": str(path)}
