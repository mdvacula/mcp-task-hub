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


# ── /metrics/runs (transcript-derived) ───────────────────────────────────────


def _transcript(path, prompt, turns, results=None):
    """Write a minimal Claude Code subagent transcript: one user prompt, then
    `turns` assistant messages each with tool calls + usage; `results` maps a
    tool_use id (t<turn><index>) to its tool_result text."""
    import json as _json

    lines = [{"type": "user", "timestamp": "2026-09-16T10:00:00.000Z", "message": {"content": prompt}}]
    t = 0
    for calls in turns:
        t += 1
        ids = [f"t{t}{i}" for i in range(len(calls))]
        lines.append({
            "type": "assistant", "timestamp": f"2026-09-16T10:0{t}:00.000Z",
            "message": {"model": "claude-sonnet-5", "usage": {"input_tokens": 100, "cache_read_input_tokens": 900, "output_tokens": 10},
                        "content": [{"type": "tool_use", "id": tid, "name": n, "input": inp} for tid, (n, inp) in zip(ids, calls)]},
        })
        if results:
            lines.append({"type": "user", "timestamp": f"2026-09-16T10:0{t}:30.000Z", "message": {"content": [
                {"type": "tool_result", "tool_use_id": tid, "content": results.get(tid, "ok")} for tid in ids]}})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(_json.dumps(l) for l in lines) + "\n")


@pytest.fixture
def transcripts_dir(tmp_path, monkeypatch):
    root = tmp_path / "transcripts"
    base = root / "-code-proj-a" / "sess" / "subagents" / "workflows"
    _transcript(base / "wf_1" / "agent-a.jsonl", "Run task c1-a (\"A\") in project repo /x — lane", [
        [("Bash", {"command": "cd /x && graft ask \"foo\" --source"}), ("Read", {"file_path": "/x/a.ts"})],
        [("Bash", {"command": "cd /x && grep -rn foo src"}), ("Edit", {"file_path": "/x/a.ts"})],
    ])
    _transcript(base / "wf_1" / "agent-b.jsonl", "Review task c1-a in /x, commit range: 1..2. Follow your protocol.", [
        [("Bash", {"command": "git diff 1..2"}), ("Bash", {"command": "cd /x && graft callers foo"})],
    ], results={"t11": "bash: graft: command not found"})
    _transcript(base / "wf_2" / "agent-c.jsonl", "In /x: map the code most relevant to this idea: \"thing\". Report", [
        [("Bash", {"command": "graft map"}), ("Bash", {"command": "graft skeleton src/a.ts"})],
    ])
    _transcript(base / "wf_2" / "agent-d.jsonl", "Adversarially critique the change at /x/openspec/changes/new-thing for COMPLETENESS", [
        [("Read", {"file_path": "/x/openspec/changes/new-thing/tasks.md"})],
    ])
    monkeypatch.setattr(server, "TRANSCRIPTS_DIR", root)
    monkeypatch.setattr(server, "CODE_ROOT", "/code")
    return root


def test_metrics_runs_drain(test_app, transcripts_dir):
    with TestClient(test_app) as client:
        rows = client.get("/metrics/runs?project=proj-a").json()
        assert sorted(r["role"] for r in rows) == ["reviewer", "worker"]
        w = next(r for r in rows if r["role"] == "worker")
        assert (w["task"], w["wf"], w["reads"], w["graft"], w["edits"], w["turns"]) == ("c1-a", "wf_1", 2, 1, 1, 2)
        assert w["in_tok"] == 2000 and w["out_tok"] == 20 and w["wall_s"] == 120
        rev = next(r for r in rows if r["role"] == "reviewer")
        assert rev["reads"] == 1  # git diff is a read-type Bash call
        assert rev["graft"] == 0  # the graft call errored (CLI missing) — not counted as graft use


def test_metrics_runs_spec(test_app, transcripts_dir):
    with TestClient(test_app) as client:
        rows = client.get("/metrics/runs?project=proj-a&phase=spec").json()
        assert sorted((r["role"], r["graft"], r["change"] or "") for r in rows) == [("spec:code-map", 2, ""), ("spec:critic", 0, "new-thing")]


def test_metrics_runs_validation(test_app, transcripts_dir):
    with TestClient(test_app) as client:
        assert client.get("/metrics/runs").status_code == 400
        assert client.get("/metrics/runs?project=proj-a&phase=nope").status_code == 400
        assert client.get("/metrics/runs?project=nope").json() == []
