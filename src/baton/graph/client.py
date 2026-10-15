"""FalkorDB access: one Store per workspace graph.

Isolation rule: the graph name is derived from the workspace id supplied by the host
(never from model output), so one workspace can never address another's graph.
"""

from __future__ import annotations

import os
import uuid
from typing import Any, List, Optional

from baton.graph.schema import INDEX_STATEMENTS

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 6379


def graph_name(workspace: str) -> str:
    """Map a workspace id to a graph name (one graph per workspace)."""
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in workspace)
    return f"baton_{safe}"


def connection_settings() -> dict:
    return {
        "host": os.environ.get("BATON_FALKORDB_HOST", DEFAULT_HOST),
        "port": int(os.environ.get("BATON_FALKORDB_PORT", DEFAULT_PORT)),
    }


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _py(value: Any) -> Any:
    """Convert driver Node/Edge objects to plain dicts."""
    props = getattr(value, "properties", None)
    if isinstance(props, dict):
        out = dict(props)
        labels = getattr(value, "labels", None)
        if labels:
            out["_label"] = labels[0]
        return out
    if isinstance(value, list):
        return [_py(v) for v in value]
    return value


class Store:
    """Handle to one workspace graph."""

    def __init__(self, workspace: str, host: Optional[str] = None, port: Optional[int] = None):
        if not workspace:
            raise ValueError("workspace is required")
        s = connection_settings()
        self.workspace = workspace
        self.graph_name = graph_name(workspace)
        self._host = host or s["host"]
        self._port = port or s["port"]
        self._client = None
        self._graph = None

    @property
    def graph(self):
        if self._graph is None:
            from falkordb import FalkorDB

            self._client = FalkorDB(host=self._host, port=self._port)
            self._graph = self._client.select_graph(self.graph_name)
        return self._graph

    def query(self, q: str, params: Optional[dict] = None):
        return self.graph.query(q, params or {})

    def ro_query(self, q: str, params: Optional[dict] = None):
        return self.graph.ro_query(q, params or {})

    def rows(self, q: str, params: Optional[dict] = None, read_only: bool = False) -> List[list]:
        """Run a query and return rows with nodes converted to dicts."""
        res = (self.ro_query if read_only else self.query)(q, params)
        return [[_py(c) for c in row] for row in res.result_set]

    def bootstrap(self) -> None:
        """Create indexes. Safe to call repeatedly."""
        from redis.exceptions import ResponseError

        for stmt in INDEX_STATEMENTS:
            try:
                self.query(stmt)
            except ResponseError as e:  # already indexed
                if "already indexed" not in str(e).lower():
                    raise

    def drop(self) -> None:
        try:
            self.graph.delete()
        except Exception:
            pass
