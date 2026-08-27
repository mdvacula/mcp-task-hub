"""Tests for HTTP endpoints (/health, /tasks, /tasks/{id}) and the MCP app."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import pytest
import hub.server as server
from hub.store import TaskStore
from starlette.applications import Starlette
from starlette.testclient import TestClient


def _app(temp_db_path, seed: bool):
    _store = TaskStore(str(temp_db_path))

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        await _store.connect()
        if seed:
            await _store.sync_task(
                id="task-1",
                title="Task 1",
                metadata={"priority": "P0"},
                project="proj-a",
            )
        old = server.store
        server.store = _store
        try:
            yield
        finally:
            server.store = old
            await _store.close()

    return Starlette(routes=list(server.http_routes), lifespan=lifespan)


@pytest.fixture
def test_app(temp_db_path):
    return _app(temp_db_path, seed=True)


@pytest.fixture
def test_app_empty(temp_db_path):
    return _app(temp_db_path, seed=False)


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
        assert tasks[0]["project"] == "proj-a"


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


def test_ui_not_built_returns_404(test_app):
    with TestClient(test_app) as client:
        resp = client.get("/ui/", follow_redirects=True)
        assert resp.status_code == 404
        assert resp.json()["error"] == "ui not built"


def test_streamable_http_app_exposes_mcp_and_custom_routes():
    app = server.mcp.streamable_http_app()
    paths = [getattr(r, "path", None) for r in app.routes]
    assert "/health" in paths
    assert "/tasks" in paths
    # the MCP transport is mounted; exact path attr differs by SDK version
    assert any(p and p.startswith("/mcp") for p in paths) or any(
        getattr(r, "path", "") == "" for r in app.routes
    )
