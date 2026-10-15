"""Decisions and conflict checks (Phase 1.5 / 1.6)."""

from __future__ import annotations

import time
from typing import Dict, Iterable, List, Optional

from baton.core.paths import normalize_paths
from baton.core.tasks import _now, goal_key
from baton.graph import queries
from baton.graph.client import Store, new_id

DECISION_KINDS = ("note", "rename", "interface", "config", "storage", "other")


def ensure_actor(store: Store, actor_id: str, kind: str = "session", now: Optional[float] = None) -> None:
    store.query(
        "MERGE (a:Actor {id: $id}) ON CREATE SET a.kind = $kind, a.started_at = $now",
        {"id": actor_id, "kind": kind, "now": _now(now)},
    )


def get_decision(store: Store, decision_id: str) -> Optional[dict]:
    rows = store.rows("MATCH (d:Decision {id: $id}) RETURN d", {"id": decision_id}, read_only=True)
    return rows[0][0] if rows else None


def decision_paths(store: Store, decision_id: str) -> List[str]:
    rows = store.rows(
        "MATCH (:Decision {id: $id})-[:ABOUT]->(a:Artifact) RETURN a.path",
        {"id": decision_id},
        read_only=True,
    )
    return [r[0] for r in rows]


def post_decision(
    store: Store,
    actor_id: str,
    text: str,
    artifacts: Iterable[str] = (),
    based_on: Iterable[str] = (),
    kind: str = "note",
    decision_id: Optional[str] = None,
    now: Optional[float] = None,
) -> dict:
    """Record a decision. `based_on` may hold decision and/or finding ids."""
    if kind not in DECISION_KINDS:
        raise ValueError("unknown decision kind: %s" % kind)
    did = decision_id or new_id("dec")
    t = _now(now)
    ensure_actor(store, actor_id, now=t)
    store.query(
        "MATCH (a:Actor {id: $actor}) "
        "CREATE (a)-[:DECIDED]->(:Decision {id: $id, text: $text, status: 'open',"
        " author: $actor, kind: $kind, created_at: $now})",
        {"actor": actor_id, "id": did, "text": text, "kind": kind, "now": t},
    )
    paths = normalize_paths(artifacts)
    if paths:
        store.query(
            "MATCH (d:Decision {id: $id}) UNWIND $paths AS p MERGE (a:Artifact {path: p})"
            " MERGE (d)-[:ABOUT]->(a)",
            {"id": did, "paths": paths},
        )
    sources = list(based_on)
    if sources:
        store.query(
            "MATCH (d:Decision {id: $id}) UNWIND $src AS sid MATCH (s:Decision {id: sid})"
            " MERGE (d)-[:BASED_ON]->(s)",
            {"id": did, "src": sources},
        )
        store.query(
            "MATCH (d:Decision {id: $id}) UNWIND $src AS sid MATCH (s:Finding {id: sid})"
            " MERGE (d)-[:BASED_ON]->(s)",
            {"id": did, "src": sources},
        )
    return get_decision(store, did)  # type: ignore[return-value]


def upsert_decision(
    store: Store,
    actor_id: str,
    decision_id: str,
    text: str,
    artifacts: Iterable[str] = (),
    kind: str = "note",
    now: Optional[float] = None,
) -> dict:
    """Create or update a decision with a caller-chosen stable id (used for derived decisions)."""
    if kind not in DECISION_KINDS:
        raise ValueError("unknown decision kind: %s" % kind)
    t = _now(now)
    ensure_actor(store, actor_id, now=t)
    store.query(
        "MERGE (d:Decision {id: $id}) "
        "ON CREATE SET d.status = 'open', d.author = $actor, d.created_at = $now "
        "SET d.text = $text, d.kind = $kind, d.updated_at = $now, d.auto = true "
        "WITH d MATCH (a:Actor {id: $actor}) MERGE (a)-[:DECIDED]->(d)",
        {"id": decision_id, "actor": actor_id, "text": text, "kind": kind, "now": t},
    )
    paths = normalize_paths(artifacts)
    if paths:
        store.query(
            "MATCH (d:Decision {id: $id}) UNWIND $paths AS p MERGE (a:Artifact {path: p})"
            " MERGE (d)-[:ABOUT]->(a)",
            {"id": decision_id, "paths": paths},
        )
    return get_decision(store, decision_id)  # type: ignore[return-value]


def supersede_decision(
    store: Store,
    actor_id: str,
    old_id: str,
    text: str,
    kind: Optional[str] = None,
    now: Optional[float] = None,
) -> dict:
    """Replace a decision: new decision inherits the old one's artifacts; old is marked superseded."""
    old = get_decision(store, old_id)
    if old is None:
        raise KeyError("decision not found: %s" % old_id)
    new = post_decision(
        store,
        actor_id,
        text,
        artifacts=decision_paths(store, old_id),
        kind=kind or old.get("kind", "note"),
        now=now,
    )
    store.query(
        "MATCH (n:Decision {id: $new}), (o:Decision {id: $old}) "
        "MERGE (n)-[:SUPERSEDES]->(o) SET o.status = 'superseded'",
        {"new": new["id"], "old": old_id},
    )
    return get_decision(store, new["id"])  # type: ignore[return-value]


def check_conflicts(
    store: Store,
    actor_id: str,
    paths: Iterable[str],
    goal: Optional[str] = None,
    task_id: Optional[str] = None,
    now: Optional[float] = None,
) -> Dict[str, object]:
    """What would collide if `actor_id` touched `paths` (or started `goal`) right now?"""
    ps = normalize_paths(paths)
    t = _now(now)
    decisions: Dict[str, dict] = {}
    for d, path in store.rows(
        queries.OPEN_DECISIONS_FOR_ARTIFACTS, {"paths": ps, "actor_id": actor_id}, read_only=True
    ) if ps else []:
        entry = decisions.setdefault(d["id"], {**d, "paths": []})
        entry["paths"].append(path)
    leases: Dict[str, dict] = {}
    for task, path in store.rows(
        queries.LIVE_LEASES_FOR_ARTIFACTS,
        {"paths": ps, "actor_id": actor_id, "now": t},
        read_only=True,
    ) if ps else []:
        entry = leases.setdefault(task["id"], {**task, "paths": []})
        entry["paths"].append(path)
    duplicates: List[dict] = []
    if goal:
        duplicates = [
            r[0]
            for r in store.rows(
                queries.DUPLICATE_TASKS,
                {"goal_key": goal_key(goal), "exclude_id": task_id or ""},
                read_only=True,
            )
            if r[0].get("owner") != actor_id
        ]
    out = {
        "paths": ps,
        "decisions": list(decisions.values()),
        "leases": list(leases.values()),
        "duplicates": duplicates,
    }
    out["has_conflicts"] = bool(out["decisions"] or out["leases"] or out["duplicates"])
    return out


def _age(seconds: float) -> str:
    seconds = int(max(0, seconds))
    if seconds < 90:
        return "%ds ago" % seconds
    if seconds < 5400:
        return "%dm ago" % (seconds // 60)
    return "%dh ago" % (seconds // 3600)


def describe_conflicts(result: Dict[str, object], now: Optional[float] = None) -> str:
    """Human-readable summary, small enough to inject as context."""
    now = time.time() if now is None else now
    lines: List[str] = []
    for d in result["decisions"]:  # type: ignore[union-attr]
        lines.append(
            "- %s decision by %s on %s: %s" % (d.get("kind", "note"), d["author"], ", ".join(d["paths"]), d["text"])
        )
    for t in result["leases"]:  # type: ignore[union-attr]
        who = str(t["owner"])[:13]
        when = ""
        if t.get("last_edit_at"):
            when = ", last edit %s" % _age(now - t["last_edit_at"])
        lines.append("- %s is working on '%s' touching %s%s" % (who, str(t["goal"])[:120], ", ".join(t["paths"]), when))
    for t in result["duplicates"]:  # type: ignore[union-attr]
        lines.append("- same ticket already %s by %s: %s" % (t["status"], t.get("owner") or "nobody", t["goal"]))
    return "\n".join(lines)
