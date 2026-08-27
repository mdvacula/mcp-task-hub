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

VALID_STATUSES = {"pending", "in-progress", "completed", "blocked"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    project     TEXT,
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


def _check_status(status: str) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status {status!r}; must be one of {sorted(VALID_STATUSES)}")


class TaskStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        db = await aiosqlite.connect(self.db_path)
        try:
            db.row_factory = aiosqlite.Row
            await db.executescript(SCHEMA)
            await self._migrate(db)
            await db.commit()
        except BaseException:
            await db.close()  # a leaked connection's thread hangs process exit
            raise
        self._db = db
        log.info("TaskStore connected: %s", self.db_path)

    async def _migrate(self, db: aiosqlite.Connection) -> None:
        # Pre-project databases lack the column; CREATE TABLE IF NOT EXISTS won't add it.
        async with db.execute("PRAGMA table_info(tasks)") as cur:
            cols = {row["name"] for row in await cur.fetchall()}
        if "project" not in cols:
            await db.execute("ALTER TABLE tasks ADD COLUMN project TEXT")
            log.info("Migrated: added tasks.project")
        # index lives here, not in SCHEMA: the column must exist first on old DBs
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project)")

    async def _ensure(self) -> None:
        if self._db is None:
            await self.connect()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

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
        project: str | None = None,
    ) -> dict:
        await self._ensure()
        if status is not None:
            _check_status(status)
        now = _now()
        async with self._db.execute("SELECT * FROM tasks WHERE id = ?", (id,)) as cur:
            existing = await cur.fetchone()

        if existing is None:
            await self._db.execute(
                "INSERT INTO tasks (id,title,status,project,metadata,created_at,updated_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (id, title, status or "pending", project, json.dumps(metadata or {}), now, now),
            )
            log.info("Created task %s", id)
        else:
            ex = self._row(existing)
            merged = {**ex["metadata"], **(metadata or {})}
            await self._db.execute(
                "UPDATE tasks SET title=?,status=?,project=?,metadata=?,updated_at=? WHERE id=?",
                (
                    title,
                    status if status is not None else ex["status"],
                    project if project is not None else ex.get("project"),
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
        project: str | None = None,
    ) -> list[dict]:
        await self._ensure()
        q, p = "SELECT * FROM tasks WHERE 1=1", []
        if id:
            q += " AND id=?"
            p.append(id)
        if status:
            q += " AND status=?"
            p.append(status)
        if project:
            q += " AND project=?"
            p.append(project)
        if change:
            q += " AND json_extract(metadata,'$.change')=?"
            p.append(change)
        async with self._db.execute(q, p) as cur:
            rows = await cur.fetchall()
        tasks = [self._row(r) for r in rows]
        tasks.sort(key=_priority_key)
        return tasks

    async def update_task_status(
        self, id: str, status: str, notes: str | None = None
    ) -> dict:
        await self._ensure()
        _check_status(status)
        if status == "blocked" and not notes:
            raise ValueError("status 'blocked' requires notes explaining the blocker")
        async with self._db.execute("SELECT * FROM tasks WHERE id=?", (id,)) as cur:
            row = await cur.fetchone()
        if not row:
            raise ValueError(f"Task not found: {id}")
        if notes:
            meta = self._row(row)["metadata"]
            meta.setdefault("statusNotes", []).append(
                {"at": _now(), "status": status, "note": notes}
            )
            await self._db.execute(
                "UPDATE tasks SET status=?,metadata=?,updated_at=? WHERE id=?",
                (status, json.dumps(meta), _now(), id),
            )
        else:
            await self._db.execute(
                "UPDATE tasks SET status=?,updated_at=? WHERE id=?",
                (status, _now(), id),
            )
        await self._db.commit()
        log.info("Status %s → %s", id, status)
        return await self.get_task(id)

    async def get_task(self, id: str) -> dict | None:
        await self._ensure()
        async with self._db.execute("SELECT * FROM tasks WHERE id=?", (id,)) as cur:
            row = await cur.fetchone()
        return self._row(row) if row else None

    async def all_tasks(self) -> list[dict]:
        await self._ensure()
        async with self._db.execute("SELECT * FROM tasks") as cur:
            rows = await cur.fetchall()
        return [self._row(r) for r in rows]

    async def task_count(self) -> int:
        await self._ensure()
        async with self._db.execute("SELECT COUNT(*) FROM tasks") as cur:
            row = await cur.fetchone()
        return row[0] if row else 0
