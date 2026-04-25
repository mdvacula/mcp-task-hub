"""
SQLite storage layer for the MCP Task Hub.
All reads and writes go through TaskStore.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import aiosqlite

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    metadata    TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_status   ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(json_extract(metadata, '$.priority'));
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _priority_key(task: dict) -> tuple:
    p = task.get("metadata", {}).get("priority", "P9")
    return ({"P0": 0, "P1": 1, "P2": 2}.get(p, 9), task.get("created_at", ""))


class TaskStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()
        log.info("TaskStore connected: %s", self.db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    def _row(self, row: aiosqlite.Row) -> dict:
        d = dict(row)
        d["metadata"] = json.loads(d.get("metadata") or "{}")
        return d

    async def sync_task(
        self,
        id: str,
        title: str,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        now = _now()
        async with self._db.execute("SELECT * FROM tasks WHERE id = ?", (id,)) as cur:
            existing = await cur.fetchone()

        if existing is None:
            await self._db.execute(
                "INSERT INTO tasks (id,title,status,metadata,created_at,updated_at)"
                " VALUES (?,?,?,?,?,?)",
                (id, title, status or "pending", json.dumps(metadata or {}), now, now),
            )
            log.info("Created task %s", id)
        else:
            ex = self._row(existing)
            merged = {**ex["metadata"], **(metadata or {})}
            await self._db.execute(
                "UPDATE tasks SET title=?,status=?,metadata=?,updated_at=? WHERE id=?",
                (
                    title,
                    status if status is not None else ex["status"],
                    json.dumps(merged),
                    now,
                    id,
                ),
            )
            log.info("Updated task %s", id)

        await self._db.commit()
        return await self.get_task(id)

    async def fetch_tasks(
        self,
        id: str | None = None,
        status: str | None = None,
        change: str | None = None,
    ) -> list[dict]:
        q, p = "SELECT * FROM tasks WHERE 1=1", []
        if id:
            q += " AND id=?"
            p.append(id)
        if status:
            q += " AND status=?"
            p.append(status)
        async with self._db.execute(q, p) as cur:
            rows = await cur.fetchall()
        tasks = [self._row(r) for r in rows]
        if change:
            tasks = [t for t in tasks if t["metadata"].get("change") == change]
        tasks.sort(key=_priority_key)
        return tasks

    async def update_task_status(self, id: str, status: str) -> dict:
        async with self._db.execute("SELECT id FROM tasks WHERE id=?", (id,)) as cur:
            if not await cur.fetchone():
                raise ValueError(f"Task not found: {id}")
        await self._db.execute(
            "UPDATE tasks SET status=?,updated_at=? WHERE id=?",
            (status, _now(), id),
        )
        await self._db.commit()
        log.info("Status %s → %s", id, status)
        return await self.get_task(id)

    async def get_task(self, id: str) -> dict | None:
        async with self._db.execute("SELECT * FROM tasks WHERE id=?", (id,)) as cur:
            row = await cur.fetchone()
        return self._row(row) if row else None

    async def all_tasks(self) -> list[dict]:
        async with self._db.execute("SELECT * FROM tasks") as cur:
            rows = await cur.fetchall()
        return [self._row(r) for r in rows]

    async def task_count(self) -> int:
        async with self._db.execute("SELECT COUNT(*) FROM tasks") as cur:
            row = await cur.fetchone()
        return row[0] if row else 0
