"""Service layer: the operations exposed to hosts, with identity and a fail-open error model.

Used by the MCP server and (Phase 3) the hook CLI. Pure Python, no MCP dependency, so it can be
tested directly.

Error model
-----------
Every public method returns a plain dict and never raises:
  {"ok": True, ...}                                   success
  {"ok": False, "error": "not_found" | "invalid"}     caller mistake, with "detail"
  {"ok": False, "degraded": True, "error": "baton_unavailable"}
                                                      store unreachable: caller should carry on
"""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any, Callable, Dict, Iterable, List, Optional

from baton.core import decisions, handoff, provenance, tasks
from baton.graph.client import Store

DEFAULT_LEASE_SECONDS = 300
MAX_TEXT = 2000
MAX_LIST = 50


def default_workspace(cwd: Optional[str] = None) -> str:
    """Stable workspace id from the host-controlled project directory (never from tool input)."""
    cwd = os.path.abspath(cwd or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    digest = hashlib.sha1(cwd.encode()).hexdigest()[:8]
    return "%s-%s" % (os.path.basename(cwd) or "root", digest)


def _clip(text: Any, n: int = MAX_TEXT) -> str:
    return str(text)[:n]


def _clean_list(items: Optional[Iterable[str]]) -> List[str]:
    return [_clip(i, 500) for i in list(items or [])[:MAX_LIST]]


class Service:
    def __init__(self, store: Store, base_actor: Optional[str] = None):
        self.store = store
        self.base_actor = (
            base_actor
            or os.environ.get("BATON_ACTOR")
            or os.environ.get("CLAUDE_CODE_SESSION_ID")  # same id the host's hooks receive
            or "session-" + uuid.uuid4().hex[:8]
        )
        self._bootstrapped = False

    # -- identity ---------------------------------------------------------
    def actor(self, label: Optional[str] = None) -> str:
        """Caller id: this process's id, optionally qualified by a free-text label (e.g. a subagent name).

        The label is an untrusted display qualifier; it never selects a workspace.
        """
        if label:
            safe = "".join(c for c in str(label)[:40] if c.isalnum() or c in "-_.")
            if safe:
                return "%s/%s" % (self.base_actor, safe)
        return self.base_actor

    # -- plumbing ---------------------------------------------------------
    def _ready(self) -> None:
        if not self._bootstrapped:
            self.store.bootstrap()
            self._bootstrapped = True

    def _safe(self, fn: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        try:
            self._ready()
            return {"ok": True, **fn()}
        except KeyError as e:
            return {"ok": False, "error": "not_found", "detail": _clip(e.args[0] if e.args else e, 200)}
        except ValueError as e:
            return {"ok": False, "error": "invalid", "detail": _clip(e, 200)}
        except Exception as e:  # store unreachable, timeout, protocol error...
            return {
                "ok": False,
                "degraded": True,
                "error": "baton_unavailable",
                "detail": "%s: %s" % (type(e).__name__, _clip(e, 160)),
            }

    # -- tasks ------------------------------------------------------------
    def create_task(self, goal: str, depends_on: Optional[List[str]] = None,
                    touches: Optional[List[str]] = None) -> Dict[str, Any]:
        def go():
            if not str(goal).strip():
                raise ValueError("goal is required")
            t = tasks.create_task(self.store, _clip(goal, 500), _clean_list(depends_on), _clean_list(touches))
            return {"task": t}
        return self._safe(go)

    def get_ready_tasks(self) -> Dict[str, Any]:
        return self._safe(lambda: {"tasks": tasks.ready_tasks(self.store)[:MAX_LIST]})

    def claim_task(self, task_id: str, lease_seconds: int = DEFAULT_LEASE_SECONDS,
                   actor: Optional[str] = None) -> Dict[str, Any]:
        def go():
            lease = max(10, min(int(lease_seconds), 3600))
            r = tasks.claim_task(self.store, task_id, self.actor(actor), lease)
            out: Dict[str, Any] = {"claimed": r.ok, "task": r.task}
            if not r.ok:
                out.update(reason=r.reason, holder=r.holder, blockers=r.blockers)
            return out
        return self._safe(go)

    def renew_lease(self, task_id: str, lease_seconds: int = DEFAULT_LEASE_SECONDS,
                    actor: Optional[str] = None) -> Dict[str, Any]:
        def go():
            lease = max(10, min(int(lease_seconds), 3600))
            return {"renewed": tasks.renew_lease(self.store, task_id, self.actor(actor), lease)}
        return self._safe(go)

    def complete_task(self, task_id: str, actor: Optional[str] = None) -> Dict[str, Any]:
        return self._safe(lambda: {"completed": tasks.complete_task(self.store, task_id, self.actor(actor))})

    def release_task(self, task_id: str, actor: Optional[str] = None) -> Dict[str, Any]:
        return self._safe(lambda: {"released": tasks.release_task(self.store, task_id, self.actor(actor))})

    # -- decisions and conflicts -------------------------------------------
    def post_decision(self, text: str, artifacts: Optional[List[str]] = None,
                      based_on: Optional[List[str]] = None, kind: str = "note",
                      actor: Optional[str] = None) -> Dict[str, Any]:
        def go():
            if not str(text).strip():
                raise ValueError("text is required")
            d = decisions.post_decision(
                self.store, self.actor(actor), _clip(text), _clean_list(artifacts),
                _clean_list(based_on), kind=kind,
            )
            return {"decision": d}
        return self._safe(go)

    def check_conflicts(self, paths: Optional[List[str]] = None, goal: Optional[str] = None,
                        task_id: Optional[str] = None, actor: Optional[str] = None) -> Dict[str, Any]:
        def go():
            res = decisions.check_conflicts(
                self.store, self.actor(actor), _clean_list(paths),
                goal=_clip(goal, 500) if goal else None, task_id=task_id,
            )
            res["summary"] = decisions.describe_conflicts(res)
            return res
        return self._safe(go)

    # -- provenance --------------------------------------------------------
    def add_finding(self, text: str, source: str, actor: Optional[str] = None) -> Dict[str, Any]:
        def go():
            if not str(text).strip():
                raise ValueError("text is required")
            return {"finding": provenance.add_finding(self.store, self.actor(actor), _clip(text), _clip(source, 300))}
        return self._safe(go)

    def why(self, decision_id: str) -> Dict[str, Any]:
        def go():
            if decisions.get_decision(self.store, decision_id) is None:
                raise KeyError("decision not found: %s" % decision_id)
            return provenance.why(self.store, decision_id)
        return self._safe(go)

    def retract(self, item_id: str, reason: str = "", actor: Optional[str] = None) -> Dict[str, Any]:
        def go():
            r = provenance.retract(self.store, item_id, self.actor(actor), _clip(reason, 500))
            return {
                "root": r["root"],
                "tainted_count": len(r["tainted"]),
                "tainted": [{"id": d["id"], "text": _clip(d["text"], 160), "author": d["author"]}
                            for d in r["tainted"]][:MAX_LIST],
            }
        return self._safe(go)

    # -- handoff -----------------------------------------------------------
    def handoff_export(self, task_id: str, actor: Optional[str] = None) -> Dict[str, Any]:
        def go():
            pk = handoff.export_handoff(self.store, task_id, self.actor(actor))
            return {"handoff_id": pk["id"], "text": pk["text"], "omitted": pk["omitted"]}
        return self._safe(go)

    def handoff_import(self, handoff_id: str, actor: Optional[str] = None) -> Dict[str, Any]:
        def go():
            pk = handoff.import_handoff(self.store, self.actor(actor), handoff_id)
            return {"handoff_id": pk["id"], "task_id": pk["task"]["id"] if pk["task"] else None,
                    "text": pk["text"]}
        return self._safe(go)
