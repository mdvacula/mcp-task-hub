# mcp-task-hub

Centralized task execution state for agentic coding workflows.
Runs as a Docker container. Agents connect via MCP over SSE.

## Quick Start

```bash
git clone https://github.com/mdvacula/mcp-task-hub ~/mcp-task-hub
cd ~/mcp-task-hub
cp .env.example .env
docker compose up -d
```

Hub is now running:
- **SSE (MCP):**  `http://localhost:8000/sse`
- **Health:**     `http://localhost:8000/health`
- **Tasks (GET):**`http://localhost:8000/tasks`

## Connect a Project

Add to `.cursor/mcp.json` in any project:

```json
{
  "mcpServers": {
    "task-hub": {
      "url": "http://localhost:8000/sse",
      "transport": "sse"
    }
  }
}
```

## MCP Tools

| Tool | Purpose |
|------|---------|
| `sync_task(id, title, status?, metadata?)` | Upsert a task |
| `fetch_tasks(id?, status?, change?)` | Query tasks |
| `update_task_status(id, status)` | Transition task status |

## Useful Commands

```bash
docker compose up -d          # start in background
docker compose down           # stop (data persists)
docker compose down -v        # stop + wipe all data
docker compose logs -f        # follow logs
docker compose up -d --build  # rebuild after update

# Inspect the database directly
docker compose exec task-hub sqlite3 /data/hub.db \
  "SELECT id, title, status FROM tasks;"
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HUB_HOST` | `0.0.0.0` | Bind address |
| `HUB_PORT` | `8000` | Exposed port |
| `HUB_DB_PATH` | `/data/hub.db` | SQLite path inside container |
| `HUB_LOG_LEVEL` | `INFO` | `DEBUG` · `INFO` · `WARNING` |

## Source

Generated from [agent-kit](https://github.com/mdvacula/agent-kit).
