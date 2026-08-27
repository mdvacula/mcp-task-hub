# mcp-task-hub

Centralized task execution state for agentic coding workflows. Runs as a Docker
container; agents connect via **MCP streamable HTTP**, humans watch through the
bundled **web UI**. One hub serves many repos — tasks are namespaced by
`project`.

This is the state store for the agent loop defined in
[`agent-kit`](https://github.com/mdvacula/agent-kit) (`/hub-spec` → `/hub-plan`
→ `/hub-drain`). See that repo's README for how the whole workflow is used;
this one covers the service itself.

## Quick start

```bash
git clone https://github.com/mdvacula/mcp-task-hub ~/infra/task-hub
cd ~/infra/task-hub
cp .env.example .env
docker compose up -d        # builds the UI (node stage) + serves (python stage)

curl http://127.0.0.1:8050/health
# → {"status":"ok","task_count":0}
```

The compose file binds **127.0.0.1:8050** (host) → 8000 (container):

| Endpoint | What |
|---|---|
| `http://127.0.0.1:8050/mcp` | MCP (streamable HTTP, stateless, JSON responses) — the only write path |
| `http://127.0.0.1:8050/ui/` | Task viewer UI (read-only) |
| `http://127.0.0.1:8050/tasks` | All tasks, JSON |
| `http://127.0.0.1:8050/tasks/{id}` | One task, JSON |
| `http://127.0.0.1:8050/health` | `{status, task_count}` |

Register with Claude Code (user-wide — every project sees it; **sessions
started before this won't have the tools**, open a new one):

```bash
claude mcp add --scope user --transport http task-hub http://127.0.0.1:8050/mcp
```

## MCP tools

| Tool | Purpose |
|------|---------|
| `sync_task(id, title, status?, metadata?, project?)` | Upsert. Creates as `pending`; merges metadata top-level keys (arrays are replaced whole — read-modify-write to append); keeps existing `project` when omitted |
| `fetch_tasks(id?, status?, change?, project?)` | Query, filters ANDed in SQL. `[]` on no match, never errors. Sorted P0→P1→P2→none, then created |
| `update_task_status(id, status, notes?)` | Transition. `blocked` **requires** `notes`; notes append `{at, status, note}` to `metadata.statusNotes` |

Statuses: `pending | in-progress | completed | blocked` (validated).

## Data model

One SQLite table (`HUB_DB_PATH`, bind-mounted at `./data/hub.db`):
`id` (stable kebab slug, `<change-id>-<task-slug>`), `title`, `status`,
`project` (owning repo dir name — first-class, indexed), `metadata` (JSON),
timestamps.

Standard metadata keys: `change` (OpenSpec change id), `specRef` (path into the
spec artifacts), `priority` (P0–P2), `type` (task|feature|chore), `tier`
(haiku|sonnet|opus — which worker model implements it), `blockedBy[]`/`blocks[]`
(task-id dependency graph), `statusNotes[]` (why-blocked history), `runLog[]`
(one entry per drain execution: tier, commit range, gates, review verdict, fix
cycles).

## The UI

Vite + React + Tailwind v4 + shadcn/ui, dark by default, served by the hub
itself at `/ui/`. Stat tiles (click to filter), project/change/status filters,
search, detail sheet showing the dependency graph, `statusNotes`, and `runLog`,
stale-claim highlighting (`in-progress` untouched >2 h), 5-second polling.

Exposing it beyond localhost: proxy **only** `/ui`, `/tasks`, `/health` —
never `/mcp`. Reference nginx vhost: `taskhub.local` on the omarchy box.

## Development

```bash
# server tests
PYTHONPATH=. uv run --no-project --with "mcp[cli]>=1.12,<2" --with aiosqlite \
  --with python-dotenv --with pytest --with pytest-asyncio --with httpx pytest -q

# UI dev server (proxies /tasks + /health to a running hub)
cd ui && pnpm install && pnpm dev

# rebuild + redeploy after changes
docker compose up -d --build
```

Pinned to `mcp[cli]>=1.12,<2` — SDK v2 renamed FastMCP and dropped
`custom_route`, which the HTTP/UI routes depend on. Don't bump casually.

## Env

| Var | Default | Purpose |
|-----|---------|---------|
| `HUB_HOST` | `0.0.0.0` | Bind address inside the container |
| `HUB_PORT` | `8000` | Container port (host port is set in compose) |
| `HUB_DB_PATH` | `/data/hub.db` | SQLite location |
| `HUB_UI_DIR` | `/app/ui` | Built UI assets |
| `HUB_LOG_LEVEL` | `INFO` | Logging |
