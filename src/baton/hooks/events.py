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

from baton.capture import derive, transcript
from baton.core import decisions, sessions
from baton.core.paths import normalize_path
from baton.core.safety import scrub
from baton.core.tasks import clip_goal
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
    d = os.path.join(tempfile.gettempdir(), "baton-%s" % (os.getuid() if hasattr(os, "getuid") else "user"))
    try:
        os.makedirs(d, mode=0o700, exist_ok=True)
    except OSError:
        pass
    return os.path.join(d, "warned-%s.json" % hashlib.sha1(actor.encode()).hexdigest()[:10])


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
        tmp = "%s.%d" % (path, os.getpid())
        with open(tmp, "w") as f:
            json.dump(seen, f)
        os.replace(tmp, path)
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
    names = ", ".join(sorted({str(d["owner"])[:8] for d in dups}))
    if sessions.designated_session(store, actor, dups):
        text = ("[baton] Another live session (%s) received this same request. You started first, so "
                "you are the one to carry it out; the other session has been told to stand down. "
                "Proceed." % names)
    else:
        text = ("[baton] Another live session (%s) received this same request and started first; it "
                "is already doing it. Do NOT implement it a second time. Reply that session %s is "
                "handling it and stop, unless the user explicitly asked for a separate attempt."
                % (names, names))
    return context_output("UserPromptSubmit", text)


def _local_modules(project: str) -> set:
    """Top-level names that belong to the project (importing them is not a new dependency)."""
    names = set()
    try:
        for entry in os.listdir(project):
            if entry.startswith("."):
                continue
            stem = os.path.splitext(entry)[0]
            names.add(entry)
            names.add(stem)
    except OSError:
        pass
    return names


_PY_FROM = re.compile(r"^[ \t]*from\s+([A-Za-z_][\w.]*)\s+import\s+([\w, ]+)", re.M)
_PY_IMPORT = re.compile(r"^[ \t]*import\s+([A-Za-z_][\w.]*)", re.M)


def related_paths(project: str, rel: str) -> List[str]:
    """Project files this file imports (best effort, python only)."""
    if not rel.endswith(".py"):
        return []
    try:
        with open(os.path.join(project, rel), errors="ignore") as f:
            text = f.read(200_000)
    except OSError:
        return []
    mods: List[str] = []
    for m in _PY_FROM.finditer(text):
        base = m.group(1)
        mods.append(base)
        for name in re.split(r"[,\s]+", m.group(2).strip()):
            if name and name != "import":
                mods.append(base + "." + name)
    for m in _PY_IMPORT.finditer(text):
        mods.append(m.group(1))
    out: List[str] = []
    for mod in mods:
        for cand in (mod.replace(".", "/") + ".py", mod.replace(".", "/") + "/__init__.py"):
            if os.path.exists(os.path.join(project, cand)) and cand not in out:
                out.append(cand)
    return out


def on_pre_tool(store: Store, payload: Dict[str, Any], cfg: Config, now: Optional[float] = None):
    project = project_dir_from(payload)
    paths = edit_paths(payload, project)
    if not paths:
        return None
    actor = actor_from(payload)
    res = decisions.check_conflicts(store, actor, paths, now=now)

    nearby: List[dict] = []
    seen_ids = set()
    for p in paths:
        for c in decisions.recent_changes_nearby(
            store, actor, p, near=related_paths(project, p), now=now
        ):
            if c["id"] not in seen_ids:
                seen_ids.add(c["id"])
                nearby.append(c)
    # a decision already reported as a same-file collision is not repeated
    same_file_ids = {d["id"] for d in res["decisions"]}  # type: ignore[union-attr]
    nearby = [c for c in nearby if c["id"] not in same_file_ids][:5]

    if not res["has_conflicts"] and not nearby:
        return None
    ids = sorted([d["id"] for d in res["decisions"]] + [t["id"] for t in res["leases"]]  # type: ignore[union-attr]
                 + [c["id"] + "@" + str(int(c["at"])) for c in nearby])
    signature = "%s|%s" % (",".join(paths), ",".join(ids))
    if cfg.policy == "warn" and _already_warned(actor, signature):
        return None
    _remember_warned(actor, signature)

    parts: List[str] = []
    if res["has_conflicts"]:
        parts.append("[baton] Possible collision on %s:\n%s\n"
                     "Their work is in progress and yours still needs doing. If your task needs something in this "
                     "file (a function, a field), add it yourself; do not assume they will, and do not call "
                     "code that does not exist yet. Re-read the file right before editing and keep their "
                     "changes. A live session on a file is not the same ticket as yours unless a 'same "
                     "ticket' line says so. Changes are recorded for you; no need to log them."
                     % (", ".join(paths), decisions.describe_conflicts(res, now=now)))
    if nearby:
        lines = ["- %s changed %s (%s): %s" % (str(c["author"])[:8], c["path"], c["kind"],
                                                scrub(c["text"], 220)) for c in nearby]
        parts.append("[baton] Other sessions recently changed files related to %s. Make sure your "
                     "edit agrees with these (names, signatures, config keys):\n%s"
                     % (", ".join(paths), "\n".join(lines)))
    text = "\n\n".join(parts)

    if res["has_conflicts"] and cfg.policy in ("ask", "deny"):
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
    tool = payload.get("tool_name")
    if cfg.capture and tool in EDIT_TOOLS and paths:
        _capture_edit(store, actor, payload, paths[0], now)
    if payload.get("tool_name") == "Bash" and len(paths) >= 2:
        decisions.post_decision(
            store, actor, "renamed/moved %s -> %s" % (paths[0], paths[1]),
            artifacts=paths, kind="rename", now=now,
        )
    return None


def _capture_edit(store: Store, actor: str, payload: Dict[str, Any], path: str, now: Optional[float]) -> None:
    """Derive decisions (interface/config/storage changes) from the edit's own payload."""
    tool = str(payload.get("tool_name"))
    inp = payload.get("tool_input") or {}
    resp = payload.get("tool_response") or {}
    if not isinstance(resp, dict) or not isinstance(inp, dict):
        return
    original = resp.get("originalFile")
    old = original if isinstance(original, str) else None
    created = resp.get("type") == "create"
    if not created and old is None:
        return  # cannot diff without the previous content
    new = derive.new_text_for_edit(tool, inp, resp, old)
    local = _local_modules(project_dir_from(payload))
    for d in derive.derive_decisions(path, None if created else old, new, local_modules=local):
        decisions.upsert_decision(
            store, actor, derive.decision_id(actor, path, d["kind"]), d["text"],
            artifacts=[path], kind=d["kind"], now=now,
        )


def _verification(payload: Dict[str, Any]) -> str:
    run = transcript.last_test_run(transcript.read_records(payload.get("transcript_path")))
    if not run:
        return ""
    tail = ": %s" % run["summary"] if run["summary"] else ""
    return "`%s` -> %s%s" % (run["command"], run["status"], tail)


def on_stop(store: Store, payload: Dict[str, Any], cfg: Config, now: Optional[float] = None):
    actor = actor_from(payload)
    note = " ".join(str(payload.get("last_assistant_message", "")).split())
    sessions.export_session_handoff(store, actor, note=note, now=now,
                                    verification=_verification(payload) if cfg.capture else "")
    if cfg.stop_check and not payload.get("stop_hook_active"):
        ov = sessions.overlapping_edits(store, actor)
        signature = "stop|" + ",".join("%s:%s" % (o["owner"], ",".join(o["paths"])) for o in ov)
        if ov and not _already_warned(actor, signature):
            _remember_warned(actor, signature)
            files = sorted({p for o in ov for p in o["paths"]})
            who = "; ".join("%s (%s)" % (str(o["owner"])[:8], scrub(clip_goal(o["goal"], 90), 90)) for o in ov[:3])
            return {"decision": "block", "reason": (
                "[baton] Before you finish: other sessions also edited files you edited (%s) while you "
                "worked: %s. Re-read those files as they are now and run the project tests. Fix any "
                "mismatch between your change and theirs (the same logic added twice, a changed "
                "return shape or signature, a lost edit), then finish." % (", ".join(files[:6]), who))}
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
