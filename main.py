"""
MCP Task Hub entry point.
Serves HTTP endpoints for health and task reads, and mounts the MCP transport.

Uses the Starlette 1.0 lifespan context manager for startup/shutdown hooks.
(on_startup / on_shutdown / on_event were removed in Starlette 1.0.)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from hub import HOST, PORT, http_routes, mcp, store

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    await store.connect()
    log.info("MCP Task Hub ready")
    log.info("Health → http://%s:%s/health", HOST, PORT)
    try:
        yield
    finally:
        await store.close()


app = Starlette(
    routes=[
        *[Route(r.path, r.endpoint) for r in http_routes],
        Mount("/", app=mcp.sse_app()),
    ],
    lifespan=lifespan,
)
# IMPORTANT: mcp.sse_app() is mounted at "/" not "/sse".
# It registers its own /sse and /messages/ routes internally.
# Mounting at "/sse" doubles the path to /sse/sse — causing 404s.
# HTTP routes are listed first so they take precedence.


if __name__ == "__main__":
    uvicorn.run("main:app", host=HOST, port=PORT,
                log_level="info", reload=False)
