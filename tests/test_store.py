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
