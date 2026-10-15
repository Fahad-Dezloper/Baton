"""Bounded handoff export and import (Phase 1.8).

A handoff is a small subgraph around a task, not a transcript: the task, what it depends on,
the artifacts it touches, and the decisions and findings that concern those artifacts.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from baton.core.tasks import _now, get_task
from baton.graph.client import Store, new_id

MAX_SUMMARY_CHARS = 8000  # stay well under the host's injected-context cap
MAX_ITEMS = 25
_ITEM_CHARS = 280

LIVE_DECISION_STATUSES = ["open", "tainted"]


def _clip(text: str, n: int = _ITEM_CHARS) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def render_packet(packet: Dict[str, object], max_chars: int = MAX_SUMMARY_CHARS) -> str:
    """Compact text form, hard-capped at max_chars."""
    task = packet["task"]
    lines: List[str] = [
        "HANDOFF %s" % packet["id"],
        "Task %s [%s]: %s" % (task["id"], task["status"], _clip(task["goal"])),  # type: ignore[index]
    ]
    if packet.get("note"):
        lines.append("Last status: %s" % _clip(packet["note"], 400))
    deps = packet.get("dependencies") or []
    if deps:
        lines.append("Depends on: " + "; ".join("%s [%s]" % (d["id"], d["status"]) for d in deps))  # type: ignore[union-attr]
    arts = packet.get("artifacts") or []
    if arts:
        lines.append("Artifacts: " + ", ".join(arts))  # type: ignore[arg-type]
    decs = packet.get("decisions") or []
    if decs:
        lines.append("Decisions:")
        for d in decs:  # type: ignore[union-attr]
            flag = "" if d["status"] == "open" else " (%s)" % d["status"]
            lines.append("- [%s]%s %s: %s" % (d.get("kind", "note"), flag, d["author"], _clip(d["text"])))
    finds = packet.get("findings") or []
    if finds:
        lines.append("Findings:")
        for f in finds:  # type: ignore[union-attr]
            flag = "" if f.get("status", "open") == "open" else " (%s)" % f["status"]
            lines.append("- %s%s (source: %s)" % (_clip(f["text"]), flag, _clip(f.get("source", ""), 80)))
    omitted = packet.get("omitted", 0)
    if omitted:
        lines.append("… %d more item(s) omitted" % omitted)
    text = "\n".join(lines)
    if len(text) > max_chars:
        cut = "\n… truncated"
        text = text[: max_chars - len(cut)] + cut
    return text


def export_handoff(
    store: Store,
    task_id: str,
    actor_id: str,
    max_items: int = MAX_ITEMS,
    max_chars: int = MAX_SUMMARY_CHARS,
    now: Optional[float] = None,
    handoff_id: Optional[str] = None,
    note: Optional[str] = None,
) -> Dict[str, object]:
    """Export a handoff. Passing `handoff_id` makes it idempotent: the same handoff is rebuilt."""
    task = get_task(store, task_id)
    if task is None:
        raise KeyError("task not found: %s" % task_id)
    t = _now(now)
    paths = [
        r[0]
        for r in store.rows(
            "MATCH (:Task {id: $id})-[:TOUCHES]->(a:Artifact) RETURN a.path ORDER BY a.path",
            {"id": task_id},
            read_only=True,
        )
    ]
    deps = [
        r[0]
        for r in store.rows(
            "MATCH (:Task {id: $id})-[:DEPENDS_ON]->(d:Task) RETURN d", {"id": task_id}, read_only=True
        )
    ]
    decisions = [
        r[0]
        for r in store.rows(
            "MATCH (d:Decision)-[:ABOUT]->(a:Artifact) WHERE a.path IN $paths AND d.status IN $st"
            " WITH DISTINCT d,"
            " CASE WHEN d.status = 'tainted' THEN 0 WHEN d.kind <> 'note' THEN 1 ELSE 2 END AS prio"
            " ORDER BY prio, d.created_at DESC LIMIT $lim RETURN d",
            {"paths": paths, "st": LIVE_DECISION_STATUSES, "lim": max_items + 1},
            read_only=True,
        )
    ] if paths else []
    omitted = max(0, len(decisions) - max_items)
    decisions = decisions[:max_items]
    findings: List[dict] = []
    if decisions:
        findings = [
            r[0]
            for r in store.rows(
                "MATCH (d:Decision) WHERE d.id IN $ids MATCH (d)-[:BASED_ON]->(f:Finding)"
                " RETURN DISTINCT f",
                {"ids": [d["id"] for d in decisions]},
                read_only=True,
            )
        ][:max_items]
    hid = handoff_id or new_id("hnd")
    store.query("MATCH (h:Handoff {id: $hid})-[r:INCLUDES]->() DELETE r", {"hid": hid})
    store.query(
        "MATCH (t:Task {id: $tid}) MERGE (h:Handoff {id: $hid})"
        " SET h.task_id = $tid, h.created_by = $actor, h.created_at = $now, h.note = $note"
        " MERGE (h)-[:INCLUDES]->(t)",
        {"tid": task_id, "hid": hid, "actor": actor_id, "now": t, "note": note or ""},
    )
    if paths:
        store.query(
            "MATCH (h:Handoff {id: $hid}) UNWIND $paths AS p MATCH (a:Artifact {path: p})"
            " MERGE (h)-[:INCLUDES]->(a)",
            {"hid": hid, "paths": paths},
        )
    if decisions:
        store.query(
            "MATCH (h:Handoff {id: $hid}) UNWIND $ids AS i MATCH (d:Decision {id: i})"
            " MERGE (h)-[:INCLUDES]->(d)",
            {"hid": hid, "ids": [d["id"] for d in decisions]},
        )
    if findings:
        store.query(
            "MATCH (h:Handoff {id: $hid}) UNWIND $ids AS i MATCH (f:Finding {id: i})"
            " MERGE (h)-[:INCLUDES]->(f)",
            {"hid": hid, "ids": [f["id"] for f in findings]},
        )
    packet: Dict[str, object] = {
        "id": hid,
        "task": task,
        "dependencies": deps,
        "artifacts": paths,
        "decisions": decisions,
        "findings": findings,
        "omitted": omitted,
        "note": note or "",
    }
    packet["text"] = render_packet(packet, max_chars)
    store.query("MATCH (h:Handoff {id: $hid}) SET h.summary = $s", {"hid": hid, "s": packet["text"]})
    return packet


def import_handoff(
    store: Store, actor_id: str, handoff_id: str, max_chars: int = MAX_SUMMARY_CHARS,
    now: Optional[float] = None,
) -> Dict[str, object]:
    """Load a handoff with *current* statuses (so retracted items show up as such)."""
    rows = store.rows(
        "MATCH (h:Handoff {id: $id}) SET h.imported_by = $actor, h.imported_at = $now RETURN h",
        {"id": handoff_id, "actor": actor_id, "now": _now(now)},
    )
    if not rows:
        raise KeyError("handoff not found: %s" % handoff_id)
    h = rows[0][0]
    task = get_task(store, h["task_id"])
    inc = store.rows(
        "MATCH (:Handoff {id: $id})-[:INCLUDES]->(x) RETURN labels(x)[0], x",
        {"id": handoff_id},
        read_only=True,
    )
    packet: Dict[str, object] = {
        "id": handoff_id,
        "task": task,
        "dependencies": [],
        "artifacts": sorted(x["path"] for kind, x in inc if kind == "Artifact"),
        "decisions": sorted((x for kind, x in inc if kind == "Decision"), key=lambda d: -d["created_at"]),
        "findings": [x for kind, x in inc if kind == "Finding"],
        "omitted": 0,
        "note": h.get("note", ""),
    }
    packet["text"] = render_packet(packet, max_chars)
    return packet
