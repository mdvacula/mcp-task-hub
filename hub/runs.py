"""Per-agent run metrics read from Claude Code subagent transcripts.

Same classification as agent-kit's scripts/hub/measure-drain.py (keep in sync):
one row per subagent transcript with its role, task, workflow id, tool-call
counts and token usage. Only aggregates leave this module — never transcript
content. The transcripts root is bind-mounted read-only (HUB_TRANSCRIPTS_DIR,
default /transcripts = ~/.claude/projects on the host); a project's transcripts
live under <root>/<encoded cwd>/*/subagents/**/agent-*.jsonl, where the encoded
cwd is the repo path with '/' replaced by '-' (e.g. -home-mdv-code-beatpath).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

READ_BASH = re.compile(
    r"^\s*(?:cd\s+\S+\s*&&\s*)?(cat|sed|head|tail|less|ls|rg|grep|find|wc|tree|jq|git\s+(?:log|diff|show|status|blame|rev-parse))\b"
)
GRAFT_ERR = re.compile(r"command not found|No such file|not built|run `?graft build|no graph|not a graft|ENOENT|Unknown command|error: unknown", re.I)
GRAFT_BASH = re.compile(r"(?:^|&&|;|\|)\s*(?:npx\s+(?:-y\s+)?(?:@nanonets/)?)?graft\s+(ask|skeleton|callers|map|grep|check|build)\b")
DRAIN_ROLE = [("Run task ", "worker"), ("Fix-cycle for task ", "fix"), ("Review task ", "reviewer"), ("Job ", "steward")]
SPEC_ROLE = [
    ("map the code most relevant", "spec:code-map"),
    ("read openspec/project.md", "spec:conventions"),
    ("hunt for constraints", "spec:constraints"),
    ("Design an implementation approach", "spec:approach"),
    ("You are judging", "spec:judge"),
    ("Author the OpenSpec change artifacts", "spec:draft"),
    ("Adversarially critique", "spec:critic"),
]
DRAIN_ROLES = ("worker", "fix", "reviewer")
SPEC_ROLES = tuple(r for _, r in SPEC_ROLE)
TASK_RE = re.compile(r"^(?:Run task|Fix-cycle for task|Review task) (\S+)")
CHANGE_RE = re.compile(r"openspec/changes/([A-Za-z0-9._-]+)")


def project_dir(root: Path, project: str, code_root: str) -> Path:
    return root / f"{code_root}/{project}".replace("/", "-")


def _first_user_text(recs: list[dict]) -> str:
    for d in recs:
        if d.get("type") != "user":
            continue
        c = (d.get("message") or {}).get("content")
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            t = " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
            if t.strip():
                return t
    return ""


def _ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def analyze(path: Path) -> dict[str, Any]:
    recs: list[dict] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                recs.append(json.loads(line))
            except ValueError:
                pass
    prompt = _first_user_text(recs)
    role = next((r for p, r in DRAIN_ROLE if prompt.startswith(p)), None) or next(
        (r for p, r in SPEC_ROLE if p in prompt[:400]), "other"
    )
    m = TASK_RE.match(prompt)
    wf = re.search(r"/workflows/(wf_[^/]+)/", str(path))
    chg = CHANGE_RE.search(prompt)
    out: dict[str, Any] = {
        "role": role, "task": m.group(1) if m else None, "wf": wf.group(1) if wf else None,
        "change": chg.group(1) if chg else None,
        "reads": 0, "graft": 0, "edits": 0, "tools": 0, "turns": 0, "in_tok": 0, "out_tok": 0,
        "model": None, "start": None, "end": None, "wall_s": None,
    }
    # tool_use id → result text, so a graft call that errored (repo not
    # indexed, CLI missing) is not counted as graft use
    results: dict[str, str] = {}
    for d in recs:
        if d.get("type") != "user":
            continue
        c = (d.get("message") or {}).get("content")
        if not isinstance(c, list):
            continue
        for x in c:
            if isinstance(x, dict) and x.get("type") == "tool_result":
                body = x.get("content")
                text = body if isinstance(body, str) else " ".join(y.get("text", "") for y in body or [] if isinstance(y, dict))
                results[x.get("tool_use_id", "")] = text
    graft_ok = lambda tid: not GRAFT_ERR.search(results.get(tid, "")[:600])
    for d in recs:
        ts = d.get("timestamp")
        if ts:
            out["start"] = out["start"] or ts
            out["end"] = ts
        if d.get("type") != "assistant":
            continue
        msg = d.get("message") or {}
        out["turns"] += 1
        out["model"] = msg.get("model") or out["model"]
        u = msg.get("usage") or {}
        out["in_tok"] += (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
        out["out_tok"] += u.get("output_tokens") or 0
        for x in msg.get("content") or []:
            if not (isinstance(x, dict) and x.get("type") == "tool_use"):
                continue
            out["tools"] += 1
            name = x.get("name", "")
            inp = x.get("input") or {}
            if name in ("Read", "Grep", "Glob"):
                out["reads"] += 1
            elif name in ("Edit", "Write", "MultiEdit"):
                out["edits"] += 1
            elif name.startswith("mcp__graft__"):
                if graft_ok(x.get("id", "")):
                    out["graft"] += 1
            elif name == "Bash":
                cmd = inp.get("command", "") or ""
                if GRAFT_BASH.search(cmd):
                    if graft_ok(x.get("id", "")):
                        out["graft"] += 1
                elif READ_BASH.match(cmd):
                    out["reads"] += 1
    a, b = _ts(out["start"]), _ts(out["end"])
    if a and b:
        out["wall_s"] = round((b - a).total_seconds())
    return out


def runs(root: Path, project: str, phase: str = "drain", since: str | None = None,
         code_root: str = "/home/mdv/code") -> list[dict[str, Any]]:
    """All classified agent runs for a project, oldest first."""
    pdir = project_dir(root, project, code_root)
    if not pdir.is_dir():
        return []
    wanted = DRAIN_ROLES if phase == "drain" else SPEC_ROLES
    rows = []
    for f in pdir.glob("*/subagents/**/agent-*.jsonl"):
        try:
            r = analyze(f)
        except OSError:
            continue
        if r["role"] not in wanted or r["turns"] == 0:
            continue
        if since and (not r["start"] or r["start"][:10] < since):
            continue
        rows.append(r)
    rows.sort(key=lambda r: (r["start"] or "", r["role"], r["task"] or ""))
    return rows


def default_root() -> Path:
    return Path(os.getenv("HUB_TRANSCRIPTS_DIR", "/transcripts"))
