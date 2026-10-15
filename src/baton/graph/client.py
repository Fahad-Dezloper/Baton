"""Thin FalkorDB connection wrapper. Implemented in Phase 1.1/1.2."""

from __future__ import annotations

import os

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


class Store:
    """Handle to one workspace graph."""

    def __init__(self, workspace: str):
        self.workspace = workspace
        self.graph_name = graph_name(workspace)

    def bootstrap(self) -> None:
        raise NotImplementedError("Phase 1.1")
