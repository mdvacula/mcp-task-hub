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


# ── /spec/{project}/{path} ───────────────────────────────────────────────────


@pytest.fixture
def repos_dir(tmp_path, monkeypatch):
    root = tmp_path / "repos"
    spec = root / "proj-a" / "openspec" / "changes" / "c1"
    spec.mkdir(parents=True)
    (spec / "tasks.md").write_text("# Tasks\n\n## 1. First thing\n\n- [ ] 1.1 do it\n")
    (root / "proj-a" / "openspec" / "notes.txt").write_text("not markdown")
    (root / "proj-a" / "README.md").write_text("outside openspec")
    (root / "proj-a" / "openspec" / "escape.md").symlink_to(root / "proj-a" / "README.md")
    (root / "secret.md").write_text("above the project")
    archived = root / "proj-a" / "openspec" / "changes" / "archive" / "old"
    archived.mkdir(parents=True)
    (archived / "tasks.md").write_text("# old")
    empty = root / "proj-b" / "openspec" / "changes" / "no-files"
    empty.mkdir(parents=True)
    monkeypatch.setattr(server, "REPOS_DIR", root)
    return root


def test_list_specs(test_app, repos_dir):
    with TestClient(test_app) as client:
        resp = client.get("/specs")
        assert resp.status_code == 200
        specs = resp.json()
        assert [(s["project"], s["change"]) for s in specs] == [("proj-a", "c1")]
        assert [f["name"] for f in specs[0]["files"]] == ["tasks.md"]
        assert specs[0]["updated"] == specs[0]["files"][0]["mtime"]


def test_list_specs_unmounted(test_app, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "REPOS_DIR", tmp_path / "absent")
    with TestClient(test_app) as client:
        assert client.get("/specs").json() == []


def test_spec_file_served(test_app, repos_dir):
    with TestClient(test_app) as client:
        resp = client.get("/spec/proj-a/openspec/changes/c1/tasks.md")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/markdown")
        assert "## 1. First thing" in resp.text


@pytest.mark.parametrize(
    "path",
    [
        "/spec/proj-a/openspec/changes/c1/missing.md",  # no such file
        "/spec/proj-a/openspec/notes.txt",  # not markdown
        "/spec/proj-a/README.md",  # outside openspec/
        "/spec/proj-a/openspec/escape.md",  # symlink escaping openspec/
        "/spec/proj-a/openspec/../../secret.md",  # traversal above the project
        "/spec/proj-a/openspec/%2e%2e/%2e%2e/secret.md",  # encoded traversal
        "/spec/nope/openspec/changes/c1/tasks.md",  # unknown project
        "/spec/../openspec/changes/c1/tasks.md",  # project traversal
    ],
)
def test_spec_file_rejects(test_app, repos_dir, path):
    with TestClient(test_app) as client:
        assert client.get(path).status_code == 404


def test_spec_file_unmounted(test_app, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "REPOS_DIR", tmp_path / "absent")
    with TestClient(test_app) as client:
        resp = client.get("/spec/proj-a/openspec/changes/c1/tasks.md")
        assert resp.status_code == 404
        assert "not mounted" in resp.json()["error"]


# ── /ui cache policy ─────────────────────────────────────────────────────────


@pytest.fixture
def ui_dir(tmp_path, monkeypatch):
    d = tmp_path / "ui"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<html>app</html>")
    (d / "assets" / "index-abc123.js").write_text("console.log(1)")
    monkeypatch.setattr(server, "UI_DIR", d)
    return d


def test_ui_index_not_cached(test_app, ui_dir):
    with TestClient(test_app) as client:
        for path in ("/ui/", "/ui/index.html", "/ui/some/spa/route"):
            resp = client.get(path)
            assert resp.status_code == 200
            assert resp.headers["cache-control"] == "no-cache"


def test_ui_assets_immutable(test_app, ui_dir):
    with TestClient(test_app) as client:
        resp = client.get("/ui/assets/index-abc123.js")
        assert resp.status_code == 200
        assert "immutable" in resp.headers["cache-control"]


# ── /metrics ─────────────────────────────────────────────────────────────────


def test_metrics_aggregates_runlog(temp_db_path):
    app = _app(temp_db_path, seed=False)
    with TestClient(app) as client:
        async def seed():
            await server.store.sync_task(
                id="c1-a", title="A", project="proj-a",
                metadata={"change": "c1", "runLog": [
                    {"tier": "sonnet", "verdict": "PASS", "fixCycles": 0, "landed": "a..b",
                     "metrics": {"worker": {"reads": 10, "graft": 3, "in_tok": 1000, "out_tok": 50, "wall_s": 100},
                                 "reviewer": {"in_tok": 400}}},
                ]},
            )
            await server.store.sync_task(
                id="c1-b", title="B", project="proj-a",
                metadata={"change": "c1", "runLog": [
                    {"tier": "opus", "verdict": "FAIL", "fixCycles": 1, "landed": None,
                     "metrics": {"worker": {"reads": 30, "graft": 0, "in_tok": 3000, "out_tok": 90, "wall_s": 300}}},
                    {"tier": "opus", "verdict": "PASS", "fixCycles": 1, "landed": "b..c"},
                ]},
            )
            await server.store.update_task_status("c1-a", "in-progress")
            await server.store.update_task_status("c1-a", "in-review")
            await server.store.update_task_status("c1-a", "completed")

        client.portal.call(seed)
        resp = client.get("/metrics")
        assert resp.status_code == 200
        (g,) = resp.json()
        assert (g["project"], g["change"], g["tasks"]) == ("proj-a", "c1", 2)
        assert g["runs"] == 3 and g["landed"] == 2 and g["reviewed"] == 3
        assert g["passFirst"] == 1 and g["fixCycles"] == 2
        assert g["metricRuns"] == 2 and g["graftRuns"] == 1
        assert g["median"]["reads"] == 20 and g["median"]["reviewerInTok"] == 400
        assert g["byTier"]["opus"]["runs"] == 2
        assert g["median"]["leadS"] is not None and g["median"]["reviewToLandS"] is not None
