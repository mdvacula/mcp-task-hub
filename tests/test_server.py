"""Tests for HTTP endpoints (/health, /tasks, /tasks/{id})."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import pytest
import hub.server as server
from hub.store import TaskStore
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.testclient import TestClient


@pytest.fixture
def test_app(temp_db_path):
    _store = TaskStore(str(temp_db_path))

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        await _store.connect()
        await _store.sync_task(
            id="task-1",
            title="Task 1",
            metadata={"priority": "P0"},
        )
        old = server.store
        server.store = _store
        try:
            yield
        finally:
            server.store = old
            await _store.close()

    return Starlette(
        routes=[*server.http_routes, Mount("/", app=server.mcp.sse_app())],
        lifespan=lifespan,
    )


@pytest.fixture
def test_app_empty(temp_db_path):
    _store = TaskStore(str(temp_db_path))

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        await _store.connect()
        old = server.store
        server.store = _store
        try:
            yield
        finally:
            server.store = old
            await _store.close()

    return Starlette(
        routes=[*server.http_routes, Mount("/", app=server.mcp.sse_app())],
        lifespan=lifespan,
    )


def test_health(test_app):
    with TestClient(test_app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["task_count"] == 1


def test_list_tasks(test_app):
    with TestClient(test_app) as client:
        resp = client.get("/tasks")
        assert resp.status_code == 200
        tasks = resp.json()
        assert len(tasks) == 1
        assert tasks[0]["id"] == "task-1"


def test_list_tasks_empty(test_app_empty):
    with TestClient(test_app_empty) as client:
        resp = client.get("/tasks")
        assert resp.status_code == 200
        assert resp.json() == []


def test_get_task(test_app):
    with TestClient(test_app) as client:
        resp = client.get("/tasks/task-1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "task-1"


def test_get_task_not_found(test_app):
    with TestClient(test_app) as client:
        resp = client.get("/tasks/nonexistent")
        assert resp.status_code == 404
        assert resp.json()["error"] == "not found"
