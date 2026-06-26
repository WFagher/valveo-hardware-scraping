"""SQLite persistence for Controller records, deduped by (vendor, model)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import Controller


class DeviceStore:
    def __init__(self, db_path: Path) -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS controllers ("
            "key TEXT PRIMARY KEY, vendor TEXT, model TEXT, data TEXT)"
        )
        self.conn.commit()

    def upsert(self, c: Controller) -> None:
        self.conn.execute(
            "INSERT INTO controllers(key, vendor, model, data) VALUES(?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET vendor=excluded.vendor, "
            "model=excluded.model, data=excluded.data",
            (c.key, c.vendor, c.model, c.model_dump_json()),
        )
        self.conn.commit()

    def get(self, key: str) -> Controller | None:
        row = self.conn.execute(
            "SELECT data FROM controllers WHERE key=?", (key,)
        ).fetchone()
        return Controller.model_validate_json(row[0]) if row else None

    def all(self) -> list[Controller]:
        rows = self.conn.execute("SELECT data FROM controllers").fetchall()
        return [Controller.model_validate_json(r[0]) for r in rows]

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM controllers").fetchone()[0]

    def close(self) -> None:
        self.conn.close()
