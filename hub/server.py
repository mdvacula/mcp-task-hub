"""
MCP Task Hub — tool definitions and HTTP health endpoints.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .store import TaskStore

load_dotenv()

log = logging.getLogger(__name__)

HOST = os.getenv("HUB_HOST", "0.0.0.0")
PORT = int(os.getenv("HUB_PORT", "8000"))
DB_PATH = os.getenv("HUB_DB_PATH", "/data/hub.db")
LOG_LEVEL = os.getenv("HUB_LOG_LEVEL", "INFO")

logging.basicConfig(level=getattr(logging, LOG_LEVEL))

store = TaskStore(DB_PATH)
mcp = FastMCP("task-hub")


# ── MCP Tools ────────────────────────────────────────────────────────────────


@mcp.tool()
async def sync_task(
    id: str,
    title: str,
    status: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict:
    """
    Upsert a task by ID.
    Creates with status 'pending' if new; merges metadata if existing.

    Args:
        id:       Stable kebab-case slug e.g. 'auth-implement-jwt'
        title:    Human-readable title
        status:   pending | in-progress | completed | blocked
        metadata: Keys: change, specRef, priority, type,
                  blockedBy, blocks, entireSessionId, notes
    """
    return await store.sync_task(id=id, title=title, status=status, metadata=metadata)


@mcp.tool()
async def fetch_tasks(
    id: str | None = None,
    status: str | None = None,
    change: str | None = None,
) -> list[dict]:
    """
    Query tasks. Returns [] on no match — never errors on empty.
    Results ordered by priority (P0 first) then creation time.

    Args:
        id:     Exact task ID
        status: pending | in-progress | completed | blocked
        change: Filter by metadata.change (OpenSpec change ID)
    """
    return await store.fetch_tasks(id=id, status=status, change=change)


@mcp.tool()
async def update_task_status(id: str, status: str) -> dict:
    """
    Transition task status. Errors if ID does not exist.

    Args:
        id:     Task to update
        status: pending | in-progress | completed | blocked
    """
    return await store.update_task_status(id=id, status=status)


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


http_routes = [
    Route("/health", health),
    Route("/tasks", list_tasks),
    Route("/tasks/{task_id:str}", get_task_endpoint),
]
