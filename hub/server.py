"""
MCP Task Hub — tool definitions, HTTP read endpoints, and the task viewer UI.

Transport is streamable HTTP (the SSE transport is deprecated). The MCP
endpoint lives at /mcp; /health, /tasks, /tasks/{id}, /specs, /spec/*, /metrics and /ui/* are plain
HTTP custom routes on the same app. The store connects lazily on first use,
so no lifespan wiring is needed in stateless mode.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from . import runs as runs_mod
from .store import TaskStore

load_dotenv()

log = logging.getLogger(__name__)

HOST = os.getenv("HUB_HOST", "0.0.0.0")
PORT = int(os.getenv("HUB_PORT", "8000"))
DB_PATH = os.getenv("HUB_DB_PATH", "/data/hub.db")
LOG_LEVEL = os.getenv("HUB_LOG_LEVEL", "INFO")
UI_DIR = Path(os.getenv("HUB_UI_DIR", "/app/ui"))
# Read-only root holding one checkout per project (project = dir name), so the
# UI can open the OpenSpec file a task's specRef points at. Mount it ro.
REPOS_DIR = Path(os.getenv("HUB_REPOS_DIR", "/repos"))
# Read-only Claude Code transcripts root (host ~/.claude/projects) for per-run
# agent metrics; only aggregates are served, never content.
TRANSCRIPTS_DIR = Path(os.getenv("HUB_TRANSCRIPTS_DIR", "/transcripts"))
CODE_ROOT = os.getenv("HUB_CODE_ROOT", "/home/mdv/code")

logging.basicConfig(level=getattr(logging, LOG_LEVEL))

store = TaskStore(DB_PATH)
mcp = FastMCP(
    "task-hub",
    host=HOST,
    port=PORT,
    stateless_http=True,
    json_response=True,
)


# ── MCP Tools ────────────────────────────────────────────────────────────────


@mcp.tool()
async def sync_task(
    id: str,
    title: str,
    status: str | None = None,
    metadata: dict[str, Any] | None = None,
    project: str | None = None,
) -> dict:
    """
    Upsert a task by ID.
    Creates with status 'pending' if new; merges metadata if existing.

    Args:
        id:       Stable kebab-case slug e.g. '<change-id>-<task-slug>'
        title:    Human-readable title
        status:   pending | in-progress | in-review | completed | blocked
        metadata: Keys: change, specRef, priority (P0|P1|P2),
                  type (task|feature|chore), tier (haiku|sonnet|opus),
                  blockedBy, blocks, runLog, notes
        project:  Repo directory name owning the task, e.g. 'newjerseybrews'
    """
    return await store.sync_task(
        id=id, title=title, status=status, metadata=metadata, project=project
    )


@mcp.tool()
async def fetch_tasks(
    id: str | None = None,
    status: str | None = None,
    change: str | None = None,
    project: str | None = None,
) -> list[dict]:
    """
    Query tasks. Returns [] on no match — never errors on empty.
    Results ordered by priority (P0 first) then creation time.

    Args:
        id:      Exact task ID
        status:  pending | in-progress | in-review | completed | blocked
        change:  Filter by metadata.change (OpenSpec change ID)
        project: Filter by owning repo, e.g. 'newjerseybrews'
    """
    return await store.fetch_tasks(id=id, status=status, change=change, project=project)


@mcp.tool()
async def update_task_status(id: str, status: str, notes: str | None = None) -> dict:
    """
    Transition task status. Errors if ID does not exist.

    Args:
        id:     Task to update
        status: pending | in-progress | in-review | completed | blocked
        notes:  Why — REQUIRED when status is 'blocked'. Appended with a
                timestamp to metadata.statusNotes.
    """
    return await store.update_task_status(id=id, status=status, notes=notes)


# ── HTTP read endpoints ───────────────────────────────────────────────────────


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "task_count": await store.task_count()})


async def list_tasks(request: Request) -> JSONResponse:
    return JSONResponse(await store.all_tasks())


async def get_task_endpoint(request: Request) -> Response:
    task = await store.get_task(request.path_params["task_id"])
    return (
        JSONResponse(task)
        if task
        else JSONResponse({"error": "not found"}, status_code=404)
    )


# ── Metrics (benchmarks aggregated from runLog + timeline) ───────────────────


def _median(xs: list[float]) -> float | None:
    xs = sorted(x for x in xs if isinstance(x, (int, float)))
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def _parse_ts(s: str | None) -> float | None:
    if not s:
        return None
    try:
        from datetime import datetime

        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _lead_seconds(timeline: list[dict], start: str, end: str) -> float | None:
    """Seconds from the first `start` transition to the last `end` transition."""
    t0 = next((_parse_ts(e.get("at")) for e in timeline if e.get("to") == start), None)
    t1 = next((_parse_ts(e.get("at")) for e in reversed(timeline) if e.get("to") == end), None)
    return (t1 - t0) if t0 is not None and t1 is not None and t1 >= t0 else None


async def metrics(request: Request) -> JSONResponse:
    """GET /metrics → per project → change benchmarks from metadata.runLog / timeline.

    Each runLog entry the drain writes may carry `metrics` ({worker, reviewer,
    fix[]} with reads/graft/edits/turns/in_tok/out_tok/wall_s, measured from
    the subagent transcripts). Groups report medians, review pass rate on the
    first try, fix-cycle totals, graft adoption, and lead times.
    """
    tasks = await store.all_tasks()
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for t in tasks:
        md = t.get("metadata") or {}
        run_log = md.get("runLog") or []
        key = (t.get("project") or "—", md.get("change") or "—")
        g = groups.setdefault(
            key,
            {
                "project": key[0], "change": key[1], "tasks": 0, "byStatus": {},
                "runs": 0, "landed": 0, "passFirst": 0, "reviewed": 0, "fixCycles": 0,
                "blockedRuns": 0, "graftRuns": 0, "metricRuns": 0,
                "_reads": [], "_graft": [], "_inTok": [], "_outTok": [], "_wall": [],
                "_revInTok": [], "_lead": [], "_review": [], "byTier": {},
            },
        )
        g["tasks"] += 1
        g["byStatus"][t["status"]] = g["byStatus"].get(t["status"], 0) + 1
        tl = md.get("timeline") or []
        lead = _lead_seconds(tl, "in-progress", "completed")
        if lead is not None:
            g["_lead"].append(lead)
        rev = _lead_seconds(tl, "in-review", "completed")
        if rev is not None:
            g["_review"].append(rev)
        for e in run_log:
            if not isinstance(e, dict):
                continue
            g["runs"] += 1
            tier = e.get("tier") or "?"
            bt = g["byTier"].setdefault(tier, {"runs": 0, "passFirst": 0, "reviewed": 0, "fixCycles": 0})
            bt["runs"] += 1
            if e.get("landed"):
                g["landed"] += 1
            if e.get("verdict") in ("PASS", "FAIL"):
                g["reviewed"] += 1
                bt["reviewed"] += 1
                if e.get("verdict") == "PASS" and not e.get("fixCycles"):
                    g["passFirst"] += 1
                    bt["passFirst"] += 1
            fc = e.get("fixCycles") or 0
            g["fixCycles"] += fc
            bt["fixCycles"] += fc
            if e.get("outcome") == "blocked":
                g["blockedRuns"] += 1
            m = e.get("metrics") or {}
            w = m.get("worker") or {}
            if w:
                g["metricRuns"] += 1
                if (w.get("graft") or 0) > 0:
                    g["graftRuns"] += 1
                for src, dst in (("reads", "_reads"), ("graft", "_graft"), ("in_tok", "_inTok"),
                                 ("out_tok", "_outTok"), ("wall_s", "_wall")):
                    if isinstance(w.get(src), (int, float)):
                        g[dst].append(w[src])
            r = m.get("reviewer") or {}
            if isinstance(r.get("in_tok"), (int, float)):
                g["_revInTok"].append(r["in_tok"])
    out = []
    for g in groups.values():
        g["median"] = {
            "reads": _median(g.pop("_reads")),
            "graftCalls": _median(g.pop("_graft")),
            "inTok": _median(g.pop("_inTok")),
            "outTok": _median(g.pop("_outTok")),
            "wallS": _median(g.pop("_wall")),
            "reviewerInTok": _median(g.pop("_revInTok")),
            "leadS": _median(g.pop("_lead")),
            "reviewToLandS": _median(g.pop("_review")),
        }
        out.append(g)
    out.sort(key=lambda g: (g["project"], g["change"]))
    return JSONResponse(out)


async def metrics_runs(request: Request) -> JSONResponse:
    """GET /metrics/runs?project=P&phase=drain|spec&since=YYYY-MM-DD

    One row per subagent run (role, task/change, workflow id, reads, graft
    calls, edits, turns, input/output tokens, wall seconds), oldest first,
    measured from the mounted transcripts. Empty list when the mount is
    absent or the project has no transcripts.
    """
    q = request.query_params
    project = q.get("project")
    if not project or "/" in project or project.startswith("."):
        return JSONResponse({"error": "project required"}, status_code=400)
    phase = q.get("phase", "drain")
    if phase not in ("drain", "spec"):
        return JSONResponse({"error": "phase must be drain or spec"}, status_code=400)
    rows = runs_mod.runs(TRANSCRIPTS_DIR, project, phase=phase, since=q.get("since"), code_root=CODE_ROOT)
    return JSONResponse(rows)


# ── Spec files (read-only, for the UI's specRef viewer) ──────────────────────


async def spec_file(request: Request) -> Response:
    """GET /spec/{project}/{path} → the markdown file at <REPOS_DIR>/<project>/<path>.

    Serves only `*.md` files under the project's `openspec/` tree; anything else
    (traversal, symlink escapes, other files) is a 404. Fragments in a specRef
    (`tasks.md#3-foo`) are the UI's business — they never reach the server.
    """
    project = request.path_params["project"]
    rel = request.path_params["path"]
    if not REPOS_DIR.is_dir():
        return JSONResponse({"error": "repos dir not mounted"}, status_code=404)
    if not project or project.startswith(".") or not rel.endswith(".md"):
        return JSONResponse({"error": "not found"}, status_code=404)
    root = (REPOS_DIR / project).resolve()
    target = (root / rel).resolve()
    if not root.is_dir() or root not in target.parents:
        return JSONResponse({"error": "not found"}, status_code=404)
    if target.relative_to(root).parts[0] != "openspec" or not target.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return Response(
        target.read_text(encoding="utf-8", errors="replace"),
        media_type="text/markdown; charset=utf-8",
        headers={"Cache-Control": "no-cache"},
    )


CHANGE_FILES = ("proposal.md", "design.md", "tasks.md")


async def list_specs(request: Request) -> JSONResponse:
    """GET /specs → every OpenSpec change dir across the mounted projects.

    [{project, change, files: [{name, size, mtime}], updated}] newest first.
    `openspec/changes/archive/` is skipped. Whether a change is queued in the
    hub is the UI's join (metadata.change), not the server's.
    """
    out: list[dict[str, Any]] = []
    if not REPOS_DIR.is_dir():
        return JSONResponse(out)
    for proj in sorted(REPOS_DIR.iterdir()):
        changes = proj / "openspec" / "changes"
        if proj.name.startswith(".") or not changes.is_dir():
            continue
        for ch in sorted(changes.iterdir()):
            if ch.name in ("archive",) or ch.name.startswith(".") or not ch.is_dir():
                continue
            files = []
            for f in sorted(ch.rglob("*.md")):
                if not f.is_file():
                    continue
                st = f.stat()
                files.append(
                    {
                        "name": str(f.relative_to(ch)),
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                    }
                )
            if not files:
                continue
            out.append(
                {
                    "project": proj.name,
                    "change": ch.name,
                    "files": files,
                    "updated": max(f["mtime"] for f in files),
                }
            )
    out.sort(key=lambda c: c["updated"], reverse=True)
    return JSONResponse(out)


# ── Task viewer UI (static SPA build, served from UI_DIR) ────────────────────


async def ui_root(request: Request) -> Response:
    return RedirectResponse("/ui/")


async def ui_file(request: Request) -> Response:
    rel = request.path_params.get("path") or "index.html"
    index = UI_DIR / "index.html"
    if not index.is_file():
        return JSONResponse({"error": "ui not built"}, status_code=404)
    target = (UI_DIR / rel).resolve()
    if UI_DIR.resolve() not in target.parents and target != UI_DIR.resolve():
        return JSONResponse({"error": "not found"}, status_code=404)
    if not target.is_file():
        target = index  # SPA fallback
    # Vite fingerprints everything under assets/, so those can be cached hard;
    # index.html must be revalidated or phones keep showing a stale bundle.
    cache = (
        "public, max-age=31536000, immutable"
        if target.parent.name == "assets" and target != index
        else "no-cache"
    )
    return FileResponse(target, headers={"Cache-Control": cache})


http_routes = [
    Route("/health", health),
    Route("/tasks", list_tasks),
    Route("/tasks/{task_id:str}", get_task_endpoint),
    Route("/specs", list_specs),
    Route("/metrics", metrics),
    Route("/metrics/runs", metrics_runs),
    Route("/spec/{project:str}/{path:path}", spec_file),
    Route("/ui", ui_root),
    Route("/ui/{path:path}", ui_file),
]

for _route in http_routes:
    mcp.custom_route(_route.path, methods=["GET"])(_route.endpoint)
