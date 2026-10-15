"""Hook event handlers (Phase 3.1 - 3.4). Pure logic over a Store; no stdin/stdout here.

Each handler returns the JSON object to print for the host, or None for "nothing to say".
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from baton.core import decisions, sessions
from baton.core.paths import normalize_path
from baton.graph.client import Store
from baton.hooks.config import Config

EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

_MV = re.compile(r"(?:^|[;&|]\s*)(?:git\s+)?mv\s+((?:-\S+\s+)*)(\S+)\s+(\S+)\s*(?:$|[;&|])")


# -- identity and paths ----------------------------------------------------------
def actor_from(payload: Dict[str, Any]) -> str:
    sid = str(payload.get("session_id") or os.environ.get("CLAUDE_CODE_SESSION_ID") or "unknown")
    agent = payload.get("agent_id")
    return "%s/%s" % (sid, str(agent)[:8]) if agent else sid


def project_dir_from(payload: Dict[str, Any]) -> str:
    return os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())


def rel_path(path: str, project: str, cwd: Optional[str] = None) -> Optional[str]:
    """Path relative to the project, or None if outside it (we do not track those)."""
    if not path:
        return None
    p = path.strip().strip("'\"")
    if not os.path.isabs(p):
        p = os.path.join(cwd or project, p)
    p = os.path.normpath(p)
    project = os.path.normpath(project)
    if p == project or not p.startswith(project + os.sep):
        return None
    return normalize_path(os.path.relpath(p, project))


def rename_pairs(command: str) -> List[Tuple[str, str]]:
    m = _MV.search(command or "")
    return [(m.group(2), m.group(3))] if m else []


def edit_paths(payload: Dict[str, Any], project: str) -> List[str]:
    tool = payload.get("tool_name")
    inp = payload.get("tool_input") or {}
    cwd = payload.get("cwd")
    raw: List[str] = []
    if tool in EDIT_TOOLS:
        raw = [inp.get("file_path") or inp.get("notebook_path") or inp.get("path") or ""]
    elif tool == "Bash":
        for src, dst in rename_pairs(str(inp.get("command", ""))):
            raw += [src, dst]
    out: List[str] = []
    for r in raw:
        rp = rel_path(r, project, cwd)
        if rp and rp not in out:
            out.append(rp)
    return out


# -- output helpers ----------------------------------------------------------------
def context_output(event: str, text: str) -> Dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def _warned_path(actor: str) -> str:
    return os.path.join(tempfile.gettempdir(), "baton-warned-%s.json" % hashlib.sha1(actor.encode()).hexdigest()[:10])


def _already_warned(actor: str, signature: str) -> bool:
    try:
        with open(_warned_path(actor)) as f:
            return signature in json.load(f)
    except (OSError, ValueError):
        return False


def _remember_warned(actor: str, signature: str) -> None:
    path = _warned_path(actor)
    try:
        try:
            with open(path) as f:
                seen = json.load(f)
        except (OSError, ValueError):
            seen = []
        seen = (seen + [signature])[-200:]
        with open(path, "w") as f:
            json.dump(seen, f)
    except OSError:
        pass


# -- handlers ----------------------------------------------------------------------
def on_session_start(store: Store, payload: Dict[str, Any], cfg: Config, now: Optional[float] = None):
    actor = actor_from(payload)
    sessions.begin_session(store, actor, now=now, lease_seconds=cfg.lease_seconds)
    text = sessions.briefing(store, actor, now=now)
    return context_output("SessionStart", text) if text else None


def on_prompt(store: Store, payload: Dict[str, Any], cfg: Config, now: Optional[float] = None):
    actor = actor_from(payload)
    goal = sessions.set_goal(store, actor, str(payload.get("prompt", "")), now=now)
    if not goal:
        return None
    dups = sessions.duplicate_sessions(store, actor, goal, now=now)
    if not dups:
        return None
    lines = ["- %s is already working on the same request: '%s'" % (str(d["owner"])[:13], str(d["goal"])[:120])
             for d in dups]
    text = ("[baton] Another live session has the same goal. Coordinate before duplicating work:\n"
            + "\n".join(lines))
    return context_output("UserPromptSubmit", text)


def on_pre_tool(store: Store, payload: Dict[str, Any], cfg: Config, now: Optional[float] = None):
    project = project_dir_from(payload)
    paths = edit_paths(payload, project)
    if not paths:
        return None
    actor = actor_from(payload)
    res = decisions.check_conflicts(store, actor, paths, now=now)
    if not res["has_conflicts"]:
        return None
    ids = sorted([d["id"] for d in res["decisions"]] + [t["id"] for t in res["leases"]])  # type: ignore[union-attr]
    signature = "%s|%s" % (",".join(paths), ",".join(ids))
    if cfg.policy == "warn" and _already_warned(actor, signature):
        return None
    _remember_warned(actor, signature)
    summary = decisions.describe_conflicts(res, now=now)
    text = ("[baton] Possible collision on %s:\n%s\n"
            "Check what the other work is doing before overwriting it. If you go ahead, record what "
            "you changed with post_decision so others can see it." % (", ".join(paths), summary))
    if cfg.policy in ("ask", "deny"):
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": cfg.policy,
            "permissionDecisionReason": text,
        }}
    return context_output("PreToolUse", text)


def on_post_tool(store: Store, payload: Dict[str, Any], cfg: Config, now: Optional[float] = None):
    project = project_dir_from(payload)
    paths = edit_paths(payload, project)
    if not paths:
        return None
    actor = actor_from(payload)
    for p in paths:
        sessions.touch(store, actor, p, now=now, lease_seconds=cfg.lease_seconds)
    if payload.get("tool_name") == "Bash" and len(paths) >= 2:
        decisions.post_decision(
            store, actor, "renamed/moved %s -> %s" % (paths[0], paths[1]),
            artifacts=paths, kind="rename", now=now,
        )
    return None


def on_stop(store: Store, payload: Dict[str, Any], cfg: Config, now: Optional[float] = None):
    actor = actor_from(payload)
    note = " ".join(str(payload.get("last_assistant_message", "")).split())
    sessions.export_session_handoff(store, actor, note=note, now=now)
    return None


def on_session_end(store: Store, payload: Dict[str, Any], cfg: Config, now: Optional[float] = None):
    sessions.end_session(store, actor_from(payload), now=now)
    return None


HANDLERS = {
    "session-start": on_session_start,
    "prompt": on_prompt,
    "pre-tool": on_pre_tool,
    "post-tool": on_post_tool,
    "stop": on_stop,
    "session-end": on_session_end,
}
