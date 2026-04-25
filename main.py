"""
MCP Task Hub entry point.
Serves HTTP endpoints for health and task reads.

Uses the Starlette 1.0 lifespan context manager for startup/shutdown hooks.
(on_startup / on_shutdown / on_event were removed in Starlette 1.0.)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route

from hub import http_routes, store, HOST, PORT

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
    routes=[Route(r.path, r.endpoint) for r in http_routes],
    lifespan=lifespan,
)


if __name__ == "__main__":
    uvicorn.run("main:app", host=HOST, port=PORT, log_level="info", reload=False)
