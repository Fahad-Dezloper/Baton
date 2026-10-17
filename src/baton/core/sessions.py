"""Implicit per-session tasks: automatic "who is working on what" without any manual commands.

Each host session (and each subagent) owns one task whose lease is renewed on every edit and
whose TOUCHES edges list the files it changed. Other sessions see it as a live lease.
"""

from __future__ import annotations

import hashlib
from typing import Dict, List, Optional

from baton.core import handoff
from baton.core.decisions import ensure_actor
from baton.core.paths import normalize_path
from baton.core.safety import scrub
from baton.core.tasks import MIN_KEY_CHARS, _now, clip_goal, goal_key
from baton.graph.client import Store

SESSION_LEASE_SECONDS = 900
BRIEFING_MAX_CHARS = 6000
BRIEFING_DECISION_WINDOW = 24 * 3600
HANDOFF_WINDOW = 7 * 24 * 3600


def session_task_id(actor: str) -> str:
    return "sess_" + hashlib.sha1(actor.encode()).hexdigest()[:12]


def handoff_id_for(actor: str) -> str:
    return "hnd_" + hashlib.sha1(actor.encode()).hexdigest()[:12]


def begin_session(store: Store, actor: str, now: Optional[float] = None,
                  lease_seconds: int = SESSION_LEASE_SECONDS) -> str:
    tid = session_task_id(actor)
    t = _now(now)
    ensure_actor(store, actor, now=t)
    store.query(
        "MERGE (t:Task {id: $id}) "
        "ON CREATE SET t.goal = $goal, t.goal_key = '', t.auto_goal = true, t.session = true,"
        " t.version = 0, t.created_at = $now "
        "SET t.status = 'claimed', t.owner = $actor, t.lease_until = $lu",
        {"id": tid, "goal": "session %s (no prompt yet)" % actor[:8], "actor": actor,
         "lu": t + lease_seconds, "now": t},
    )
    return tid


def touch(store: Store, actor: str, path: str, now: Optional[float] = None,
          lease_seconds: int = SESSION_LEASE_SECONDS) -> None:
    """Record that `actor` just edited `path`; renews its lease."""
    p = normalize_path(path)
    if not p:
        return
    t = _now(now)
    begin_session(store, actor, now=t, lease_seconds=lease_seconds)
    store.query(
        "MATCH (t:Task {id: $id}) MERGE (a:Artifact {path: $p}) MERGE (t)-[:TOUCHES]->(a) "
        "SET t.lease_until = $lu, t.last_edit_at = $now, t.last_edit_path = $p",
        {"id": session_task_id(actor), "p": p, "lu": t + lease_seconds, "now": t},
    )


def set_goal(store: Store, actor: str, prompt: str, now: Optional[float] = None) -> Optional[str]:
    """First prompt becomes the session's goal. Returns the goal if it was set now."""
    full = " ".join(scrub(prompt).split())
    if not full:
        return None
    goal = full[:600]
    begin_session(store, actor, now=now)
    rows = store.rows(
        "MATCH (t:Task {id: $id}) WHERE t.auto_goal = true "
        "SET t.goal = $goal, t.goal_key = $gk, t.auto_goal = false RETURN t.goal",
        {"id": session_task_id(actor), "goal": goal, "gk": goal_key(full)},
    )
    return full if rows else None


def duplicate_sessions(store: Store, actor: str, goal: str, now: Optional[float] = None) -> List[dict]:
    """Other live sessions whose request matches this one (`goal` is the full prompt text)."""
    t = _now(now)
    if len(goal_key(goal)) < MIN_KEY_CHARS:
        return []
    return [
        r[0]
        for r in store.rows(
            "MATCH (t:Task {goal_key: $gk, status: 'claimed'}) "
            "WHERE t.owner <> $actor AND t.lease_until >= $now RETURN t",
            {"gk": goal_key(goal), "actor": actor, "now": t},
            read_only=True,
        )
    ]


def designated_session(store: Store, actor: str, dups: List[dict]) -> bool:
    """Among sessions given the same request, exactly one proceeds: earliest start, then smallest id.

    Every session computes the same order from the same data, so the others can stand down.
    """
    mine = store.rows(
        "MATCH (t:Task {id: $id}) RETURN t.created_at", {"id": session_task_id(actor)}, read_only=True
    )
    my_key = (mine[0][0] if mine and mine[0][0] is not None else float("inf"), actor)
    others = [(d.get("created_at", float("inf")), str(d.get("owner", ""))) for d in dups]
    return all(my_key <= o for o in others)


def end_session(store: Store, actor: str, now: Optional[float] = None) -> None:
    store.query(
        "MATCH (t:Task {id: $id}) SET t.status = 'done', t.lease_until = 0, t.done_at = $now",
        {"id": session_task_id(actor), "now": _now(now)},
    )


def export_session_handoff(store: Store, actor: str, note: str = "", now: Optional[float] = None,
                           verification: str = ""):
    begin_session(store, actor, now=now)
    if verification:
        store.query("MATCH (t:Task {id: $id}) SET t.verification = $v",
                    {"id": session_task_id(actor), "v": verification[:300]})
    return handoff.export_handoff(
        store, session_task_id(actor), actor, now=now,
        handoff_id=handoff_id_for(actor), note=scrub(note, 600),
    )


def briefing(store: Store, actor: str, now: Optional[float] = None,
             max_chars: int = BRIEFING_MAX_CHARS) -> str:
    """What a session should know when it starts. Empty string when there is nothing to say."""
    t = _now(now)
    parts: List[str] = []

    live = store.rows(
        "MATCH (t:Task {status: 'claimed'}) WHERE t.owner <> $actor AND t.lease_until >= $now "
        "AND NOT coalesce(t.auto_goal, false) "
        "OPTIONAL MATCH (t)-[:TOUCHES]->(a:Artifact) "
        "WITH t, collect(a.path)[..6] AS paths ORDER BY t.last_edit_at DESC LIMIT 5 RETURN t, paths",
        {"actor": actor, "now": t},
        read_only=True,
    )
    if live:
        parts.append("Other sessions working now:")
        for task, paths in live:
            parts.append("- %s: %s%s" % (str(task["owner"])[:13], clip_goal(task["goal"], 160),
                                         " (touching %s)" % ", ".join(paths) if paths else ""))

    decs = store.rows(
        "MATCH (d:Decision) WHERE d.status IN ['open', 'tainted'] AND d.author <> $actor "
        "AND d.created_at >= $since "
        "WITH d, CASE WHEN d.status = 'tainted' THEN 0 WHEN d.kind <> 'note' THEN 1 ELSE 2 END AS prio "
        "ORDER BY prio, d.created_at DESC LIMIT 8 RETURN d",
        {"actor": actor, "since": t - BRIEFING_DECISION_WINDOW},
        read_only=True,
    )
    if decs:
        parts.append("Recent decisions by others:")
        for (d,) in decs:
            flag = " (TAINTED: based on a retracted source)" if d["status"] == "tainted" else ""
            parts.append("- [%s]%s %s" % (d.get("kind", "note"), flag, scrub(d["text"], 200)))

    last = store.rows(
        "MATCH (h:Handoff) WHERE h.created_by <> $actor AND h.created_at >= $since "
        "RETURN h.id ORDER BY h.created_at DESC LIMIT 1",
        {"actor": actor, "since": t - HANDOFF_WINDOW},
        read_only=True,
    )
    if last:
        pk = handoff.import_handoff(store, actor, last[0][0], max_chars=3000, now=t)
        parts.append("Latest handoff from a previous session:")
        parts.append(pk["text"])  # type: ignore[arg-type]

    if not parts:
        return ""
    text = "[baton] Coordination context for this repository:\n" + "\n".join(parts)
    if len(text) > max_chars:
        text = text[: max_chars - 14] + "\n… truncated"
    return text
