from __future__ import annotations

import sqlite3
from pathlib import Path


class SearchIndex:
    """Disposable SQLite FTS5 index rebuilt from authoritative JSON records."""

    def __init__(self, memory_root: Path):
        self.path = memory_root / "cache" / "index.sqlite3"

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA trusted_schema=OFF")
        return connection

    def _init(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS records USING fts5(kind, record_id UNINDEXED, title, body)")

    def rebuild(self, records: list[dict]) -> int:
        self._init()
        with self._connect() as db:
            db.execute("DELETE FROM records")
            for record in records:
                db.execute(
                    "INSERT INTO records(kind, record_id, title, body) VALUES (?, ?, ?, ?)",
                    (record["kind"], record["record_id"], record.get("title", ""), record.get("body", "")),
                )
            return len(records)

    def search(self, query: str, *, kind: str | None = None, limit: int = 50) -> list[dict]:
        if not query.strip():
            return []
        self._init()
        limit = max(1, min(limit, 200))
        sql = "SELECT kind, record_id, title, body, bm25(records) AS rank FROM records WHERE records MATCH ?"
        params: list[object] = [query]
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        with self._connect() as db:
            rows = db.execute(sql, params).fetchall()
        return ["kind" and {"kind": r[0], "record_id": r[1], "title": r[2], "body": r[3], "rank": r[4]} for r in rows]
