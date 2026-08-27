"""
MCP Task Hub entry point.

Runs FastMCP's streamable-HTTP transport directly: the MCP endpoint is /mcp,
and /health, /tasks, /tasks/{id}, /ui/* are custom routes on the same app.
Host/port come from HUB_HOST/HUB_PORT (see hub/server.py).
"""
from hub import mcp

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
