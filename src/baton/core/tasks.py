"""Tasks and leases (Phase 1.3 / 1.4)."""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from baton.core.paths import normalize_paths
from baton.graph import queries
from baton.graph.client import Store, new_id

LEASE_SECONDS_DEFAULT = 300


def goal_key(goal: str) -> str:
    """Normalized goal text used to spot duplicate tickets.

    Computed from the FULL text: long texts are hashed so two requests that merely share a long
    preamble are not mistaken for duplicates.
    """
    norm = re.sub(r"[^a-z0-9]+", " ", goal.lower()).strip()
    if len(norm) <= 200:
        return norm
    return "h:" + hashlib.sha1(norm.encode()).hexdigest()


def _now(now: Optional[float]) -> float:
    return time.time() if now is None else now


@dataclass
class ClaimResult:
    ok: bool
    task: Optional[dict] = None
    reason: str = ""          # not_found | done | held | blocked | not_claimable
    holder: str = ""
    blockers: List[dict] = field(default_factory=list)


def get_task(store: Store, task_id: str) -> Optional[dict]:
    rows = store.rows(queries.GET_TASK, {"task_id": task_id}, read_only=True)
    return rows[0][0] if rows else None


def create_task(
    store: Store,
    goal: str,
    depends_on: Iterable[str] = (),
    touches: Iterable[str] = (),
    task_id: Optional[str] = None,
    now: Optional[float] = None,
) -> dict:
    tid = task_id or new_id("task")
    store.query(
        "CREATE (:Task {id: $id, goal: $goal, goal_key: $gk, status: 'open', owner: '',"
        " lease_until: 0, version: 0, created_at: $now})",
        {"id": tid, "goal": goal, "gk": goal_key(goal), "now": _now(now)},
    )
    deps = list(depends_on)
    if deps:
        store.query(
            "MATCH (t:Task {id: $id}) UNWIND $deps AS did MATCH (d:Task {id: did})"
            " MERGE (t)-[:DEPENDS_ON]->(d)",
            {"id": tid, "deps": deps},
        )
    paths = normalize_paths(touches)
    if paths:
        store.query(
            "MATCH (t:Task {id: $id}) UNWIND $paths AS p MERGE (a:Artifact {path: p})"
            " MERGE (t)-[:TOUCHES]->(a)",
            {"id": tid, "paths": paths},
        )
    return get_task(store, tid)  # type: ignore[return-value]


def ready_tasks(store: Store) -> List[dict]:
    return [r[0] for r in store.rows(queries.READY_TASKS, read_only=True)]


def claim_task(
    store: Store,
    task_id: str,
    actor_id: str,
    lease_seconds: int = LEASE_SECONDS_DEFAULT,
    now: Optional[float] = None,
) -> ClaimResult:
    t = _now(now)
    rows = store.rows(
        queries.CLAIM_TASK,
        {"task_id": task_id, "actor_id": actor_id, "now": t, "lease_until": t + lease_seconds},
    )
    if rows:
        return ClaimResult(True, rows[0][0])
    # Not claimed: explain why, from a read.
    task = get_task(store, task_id)
    if task is None:
        return ClaimResult(False, reason="not_found")
    if task["status"] == "done":
        return ClaimResult(False, task, reason="done")
    if task["status"] == "claimed" and task["lease_until"] >= t:
        return ClaimResult(False, task, reason="held", holder=task["owner"])
    blockers = [
        {"id": r[0], "goal": r[1], "status": r[2]}
        for r in store.rows(queries.TASK_BLOCKERS, {"task_id": task_id}, read_only=True)
    ]
    if blockers:
        return ClaimResult(False, task, reason="blocked", blockers=blockers)
    return ClaimResult(False, task, reason="not_claimable")


def renew_lease(
    store: Store, task_id: str, actor_id: str, lease_seconds: int = LEASE_SECONDS_DEFAULT,
    now: Optional[float] = None,
) -> bool:
    t = _now(now)
    rows = store.rows(
        queries.RENEW_LEASE,
        {"task_id": task_id, "actor_id": actor_id, "now": t, "lease_until": t + lease_seconds},
    )
    return bool(rows)


def complete_task(store: Store, task_id: str, actor_id: str, now: Optional[float] = None) -> bool:
    rows = store.rows(
        queries.COMPLETE_TASK, {"task_id": task_id, "actor_id": actor_id, "now": _now(now)}
    )
    return bool(rows)


def release_task(store: Store, task_id: str, actor_id: str) -> bool:
    rows = store.rows(queries.RELEASE_TASK, {"task_id": task_id, "actor_id": actor_id})
    return bool(rows)
