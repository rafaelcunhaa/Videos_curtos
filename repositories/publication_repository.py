"""Persistência local de estado de publicação; não decide retry nem chama providers."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PublicationRepository:
    """Repository JSONL incremental, compatível com o armazenamento local atual."""

    def __init__(self, store_path: str = ".pipeline_cache/publications.jsonl"):
        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _read_all(self) -> list[dict[str, Any]]:
        if not self.store_path.exists():
            return []
        records = []
        with self.store_path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    records.append(json.loads(line))
        return records

    def _write_all(self, records: list[dict[str, Any]]) -> None:
        temporary = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        temporary.replace(self.store_path)

    def get(self, publication_key: str) -> dict[str, Any] | None:
        matches = [r for r in self._read_all() if r.get("publication_key") == publication_key]
        return matches[-1] if matches else None

    def create_or_get(self, record: dict[str, Any]) -> dict[str, Any]:
        existing = self.get(record["publication_key"])
        if existing is not None:
            return existing
        record = dict(record)
        record.setdefault("created_at", self._now())
        record.setdefault("updated_at", record["created_at"])
        records = self._read_all()
        records.append(record)
        self._write_all(records)
        return record

    def update(self, publication_key: str, **changes: Any) -> dict[str, Any]:
        records = self._read_all()
        for index, record in enumerate(records):
            if record.get("publication_key") == publication_key:
                record.update(changes)
                record["updated_at"] = self._now()
                records[index] = record
                self._write_all(records)
                return record
        raise KeyError(f"Publication not found: {publication_key}")

    def list_recoverable(self, older_than: str | None = None) -> list[dict[str, Any]]:
        states = {"IN_PROGRESS", "UNKNOWN"}
        records = [r for r in self._read_all() if r.get("status") in states]
        if older_than is not None:
            records = [r for r in records if r.get("updated_at", "") < older_than]
        return records
