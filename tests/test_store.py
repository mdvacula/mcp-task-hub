"""Tests for the TaskStore storage layer."""

import pytest
from hub.store import TaskStore


@pytest.fixture
async def store(temp_db_path):
    s = TaskStore(str(temp_db_path))
    await s.connect()
    yield s
    await s.close()


async def test_create_task(store):
    task = await store.sync_task(id="task-1", title="Task One")
    assert task["id"] == "task-1"
    assert task["title"] == "Task One"
    assert task["status"] == "pending"
    assert task["metadata"] == {}


async def test_update_existing_task_merges_metadata(store):
    await store.sync_task(id="task-1", title="Task One", metadata={"priority": "P0"})
    updated = await store.sync_task(
        id="task-1", title="Task One Updated", metadata={"change": "ch-1"}
    )
    assert updated["title"] == "Task One Updated"
    assert updated["metadata"]["priority"] == "P0"
    assert updated["metadata"]["change"] == "ch-1"


async def test_filter_by_status(store):
    await store.sync_task(id="a", title="A", status="pending")
    await store.sync_task(id="b", title="B", status="in-progress")
    pending = await store.fetch_tasks(status="pending")
    assert len(pending) == 1
    assert pending[0]["id"] == "a"


async def test_filter_by_id(store):
    await store.sync_task(id="a", title="A")
    await store.sync_task(id="b", title="B")
    result = await store.fetch_tasks(id="b")
    assert len(result) == 1
    assert result[0]["id"] == "b"


async def test_filter_by_change(store):
    await store.sync_task(id="a", title="A", metadata={"change": "ch-1"})
    await store.sync_task(id="b", title="B", metadata={"change": "ch-2"})
    result = await store.fetch_tasks(change="ch-1")
    assert len(result) == 1
    assert result[0]["id"] == "a"


async def test_priority_ordering(store):
    await store.sync_task(id="low", title="Low", metadata={"priority": "P2"})
    await store.sync_task(id="high", title="High", metadata={"priority": "P0"})
    await store.sync_task(id="mid", title="Mid", metadata={"priority": "P1"})
    tasks = await store.fetch_tasks()
    ids = [t["id"] for t in tasks]
    assert ids == ["high", "mid", "low"]


async def test_update_task_status(store):
    await store.sync_task(id="task-1", title="T")
    updated = await store.update_task_status(id="task-1", status="completed")
    assert updated["status"] == "completed"


async def test_update_task_status_missing_raises(store):
    with pytest.raises(ValueError, match="Task not found"):
        await store.update_task_status(id="nonexistent", status="completed")


async def test_task_count(store):
    assert await store.task_count() == 0
    await store.sync_task(id="x", title="X")
    assert await store.task_count() == 1


async def test_fetch_returns_empty_on_no_match(store):
    result = await store.fetch_tasks(status="pending")
    assert result == []


async def test_filter_by_project(store):
    await store.sync_task(id="a", title="A", project="proj-a")
    await store.sync_task(id="b", title="B", project="proj-b")
    await store.sync_task(id="c", title="C")  # no project
    result = await store.fetch_tasks(project="proj-a")
    assert [t["id"] for t in result] == ["a"]
    assert len(await store.fetch_tasks()) == 3


async def test_project_preserved_on_update_without_project(store):
    await store.sync_task(id="a", title="A", project="proj-a")
    updated = await store.sync_task(id="a", title="A2")
    assert updated["project"] == "proj-a"
    assert updated["title"] == "A2"


async def test_blocked_requires_notes(store):
    await store.sync_task(id="a", title="A")
    with pytest.raises(ValueError, match="requires notes"):
        await store.update_task_status(id="a", status="blocked")


async def test_blocked_with_notes_appends_status_notes(store):
    await store.sync_task(id="a", title="A")
    updated = await store.update_task_status(
        id="a", status="blocked", notes="missing API key"
    )
    assert updated["status"] == "blocked"
    notes = updated["metadata"]["statusNotes"]
    assert len(notes) == 1
    assert notes[0]["note"] == "missing API key"
    assert notes[0]["status"] == "blocked"
    # a second transition appends rather than overwrites
    updated = await store.update_task_status(id="a", status="pending", notes="unblocked")
    assert len(updated["metadata"]["statusNotes"]) == 2


async def test_invalid_status_rejected(store):
    await store.sync_task(id="a", title="A")
    with pytest.raises(ValueError, match="Invalid status"):
        await store.update_task_status(id="a", status="done")
    with pytest.raises(ValueError, match="Invalid status"):
        await store.sync_task(id="b", title="B", status="wip")


async def test_migration_adds_project_column(temp_db_path):
    import aiosqlite

    # build a pre-project database by hand
    db = await aiosqlite.connect(str(temp_db_path))
    await db.executescript(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY, title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        INSERT INTO tasks VALUES ('old-1','Old','pending','{}','2026-01-01','2026-01-01');
        """
    )
    await db.commit()
    await db.close()

    s = TaskStore(str(temp_db_path))
    await s.connect()
    try:
        task = await s.get_task("old-1")
        assert task["project"] is None
        migrated = await s.sync_task(id="old-1", title="Old", project="proj-a")
        assert migrated["project"] == "proj-a"
    finally:
        await s.close()
