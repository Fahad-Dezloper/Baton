"""Findings, why-traces and retraction (Phase 1.7)."""

from __future__ import annotations

from typing import Dict, List, Optional

from baton.core.decisions import ensure_actor, get_decision
from baton.core.tasks import _now
from baton.graph import queries
from baton.graph.client import Store, new_id


def add_finding(
    store: Store,
    actor_id: str,
    text: str,
    source: str,
    confidence: float = 1.0,
    finding_id: Optional[str] = None,
    now: Optional[float] = None,
) -> dict:
    fid = finding_id or new_id("fnd")
    ensure_actor(store, actor_id, now=now)
    store.query(
        "CREATE (:Finding {id: $id, text: $text, source: $source, confidence: $conf,"
        " status: 'open', author: $actor, created_at: $now})",
        {"id": fid, "text": text, "source": source, "conf": confidence, "actor": actor_id, "now": _now(now)},
    )
    return get_finding(store, fid)  # type: ignore[return-value]


def get_finding(store: Store, finding_id: str) -> Optional[dict]:
    rows = store.rows("MATCH (f:Finding {id: $id}) RETURN f", {"id": finding_id}, read_only=True)
    return rows[0][0] if rows else None


def why(store: Store, decision_id: str) -> Dict[str, List[dict]]:
    """Everything a decision was (transitively) based on."""
    return {
        "decisions": [r[0] for r in store.rows(queries.WHY_DECISIONS, {"id": decision_id}, read_only=True)],
        "findings": [r[0] for r in store.rows(queries.WHY_FINDINGS, {"id": decision_id}, read_only=True)],
    }


def blast_radius(store: Store, item_id: str) -> List[dict]:
    """Decisions derived (transitively) from a decision or finding."""
    if get_decision(store, item_id) is not None:
        rows = store.rows(queries.BLAST_FROM_DECISION, {"id": item_id}, read_only=True)
    else:
        rows = store.rows(queries.BLAST_FROM_FINDING, {"id": item_id}, read_only=True)
    return [r[0] for r in rows]


def retract(
    store: Store,
    item_id: str,
    actor_id: str,
    reason: str = "",
    now: Optional[float] = None,
) -> Dict[str, object]:
    """Mark a decision or finding wrong and taint everything derived from it.

    Returns {"root": ..., "tainted": [decision dicts that were open and are now tainted],
             "affected": [all derived decision dicts]}.
    """
    t = _now(now)
    is_decision = get_decision(store, item_id) is not None
    label = "Decision" if is_decision else "Finding"
    if not is_decision and get_finding(store, item_id) is None:
        raise KeyError("item not found: %s" % item_id)
    affected = blast_radius(store, item_id)
    store.query(
        "MATCH (x:%s {id: $id}) SET x.status = 'retracted', x.retracted_by = $actor,"
        " x.retract_reason = $reason, x.retracted_at = $now" % label,
        {"id": item_id, "actor": actor_id, "reason": reason, "now": t},
    )
    ids = [d["id"] for d in affected]
    if ids:
        store.query(
            "MATCH (d:Decision) WHERE d.id IN $ids AND d.status = 'open'"
            " SET d.status = 'tainted', d.tainted_by = $root, d.tainted_at = $now",
            {"ids": ids, "root": item_id, "now": t},
        )
    after = (get_decision if is_decision else get_finding)(store, item_id)
    tainted = [d for d in affected if d.get("status") == "open"]
    return {"root": after, "tainted": tainted, "affected": affected}
