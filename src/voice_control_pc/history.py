"""Bounded local command history. No audio or confirmation tokens are retained."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class HistoryStore:
    def __init__(self, path: Path, limit: int = 100):
        self.path, self.limit = path, limit

    def read(self) -> list[dict]:
        if not self.path.is_file():
            return []
        rows = []
        for line in self.path.read_text("utf-8").splitlines():
            try:
                row = json.loads(line)
                if isinstance(row, dict) and all(
                    k in row for k in ("time", "text", "message", "status")
                ):
                    rows.append(row)
            except ValueError:
                continue
        return rows[-self.limit :]

    def append(self, text: str, result) -> dict:
        row = {
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "text": text,
            "message": result.message,
            "status": result.status,
        }
        rows = [*self.read(), row][-self.limit :]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows), "utf-8"
        )
        temporary.replace(self.path)
        return row

    def clear(self):
        self.path.unlink(missing_ok=True)
