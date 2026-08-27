"""
MCP Task Hub — tool definitions, HTTP read endpoints, and the task viewer UI.

Transport is streamable HTTP (the SSE transport is deprecated). The MCP
endpoint lives at /mcp; /health, /tasks, /tasks/{id} and /ui/* are plain
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

from .store import TaskStore

load_dotenv()

log = logging.getLogger(__name__)

HOST = os.getenv("HUB_HOST", "0.0.0.0")
PORT = int(os.getenv("HUB_PORT", "8000"))
DB_PATH = os.getenv("HUB_DB_PATH", "/data/hub.db")
LOG_LEVEL = os.getenv("HUB_LOG_LEVEL", "INFO")
UI_DIR = Path(os.getenv("HUB_UI_DIR", "/app/ui"))

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
        status:   pending | in-progress | completed | blocked
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
        status:  pending | in-progress | completed | blocked
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
        status: pending | in-progress | completed | blocked
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
    return FileResponse(target)


http_routes = [
    Route("/health", health),
    Route("/tasks", list_tasks),
    Route("/tasks/{task_id:str}", get_task_endpoint),
    Route("/ui", ui_root),
    Route("/ui/{path:path}", ui_file),
]

for _route in http_routes:
    mcp.custom_route(_route.path, methods=["GET"])(_route.endpoint)
