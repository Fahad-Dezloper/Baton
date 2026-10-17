"""MCP tool surface (Phase 2). Thin shell over baton.service.Service.

Run:  python -m baton.mcp_server.server        (stdio)
Env:  BATON_WORKSPACE   workspace id (default: derived from the working directory)
      BATON_ACTOR       caller id for this process (default: random per process)
      BATON_FALKORDB_HOST / BATON_FALKORDB_PORT

Never write to stdout here: stdout is the protocol channel.
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional

from mcp.server.mcpserver import MCPServer

from baton.graph.client import Store
from baton.service import Service, default_workspace

TOOL_NAMES = (
    "create_task",
    "get_ready_tasks",
    "claim_task",
    "renew_lease",
    "complete_task",
    "release_task",
    "post_decision",
    "check_conflicts",
    "add_finding",
    "why",
    "retract",
    "handoff_export",
    "handoff_import",
)

INSTRUCTIONS = (
    "baton coordinates parallel sessions working in one repository. Before editing files that "
    "others may be touching, call check_conflicts. Claim a task before working on it and complete "
    "it when done. Record choices that affect others with post_decision (set `kind` for renames, "
    "config or interface changes). Results with degraded=true mean the coordination store is "
    "unavailable: continue your work normally."
)


def build_server(service: Optional[Service] = None) -> MCPServer:
    if service is None:
        ws = os.environ.get("BATON_WORKSPACE") or default_workspace()
        service = Service(Store(ws))
    svc = service
    mcp = MCPServer("baton", instructions=INSTRUCTIONS)

    @mcp.tool()
    def create_task(goal: str, depends_on: Optional[List[str]] = None,
                    touches: Optional[List[str]] = None) -> dict:
        """Create a task. `touches` lists file paths it will change; `depends_on` lists task ids."""
        return svc.create_task(goal, depends_on, touches)

    @mcp.tool()
    def get_ready_tasks() -> dict:
        """List open tasks whose dependencies are all done."""
        return svc.get_ready_tasks()

    @mcp.tool()
    def claim_task(task_id: str, lease_seconds: int = 300, actor: Optional[str] = None) -> dict:
        """Take a task with a time-limited lease. Fails with a reason if held, blocked or done."""
        return svc.claim_task(task_id, lease_seconds, actor)

    @mcp.tool()
    def renew_lease(task_id: str, lease_seconds: int = 300, actor: Optional[str] = None) -> dict:
        """Extend your lease on a task you hold."""
        return svc.renew_lease(task_id, lease_seconds, actor)

    @mcp.tool()
    def complete_task(task_id: str, actor: Optional[str] = None) -> dict:
        """Mark a task you hold as done."""
        return svc.complete_task(task_id, actor)

    @mcp.tool()
    def release_task(task_id: str, actor: Optional[str] = None) -> dict:
        """Give up a task you hold so someone else can take it."""
        return svc.release_task(task_id, actor)

    @mcp.tool()
    def post_decision(text: str, artifacts: Optional[List[str]] = None,
                      based_on: Optional[List[str]] = None, kind: str = "note",
                      actor: Optional[str] = None) -> dict:
        """Rarely needed: edits, renames and interface/config/storage changes are recorded automatically. Use only for a design decision not visible in a diff. kind: note|rename|interface|config|storage|other."""
        return svc.post_decision(text, artifacts, based_on, kind, actor)

    @mcp.tool()
    def check_conflicts(paths: Optional[List[str]] = None, goal: Optional[str] = None,
                        task_id: Optional[str] = None, actor: Optional[str] = None) -> dict:
        """Rarely needed: every edit is checked automatically. Use to ask about files you have not touched yet, or a `goal` you are about to start."""
        return svc.check_conflicts(paths, goal, task_id, actor)

    @mcp.tool()
    def add_finding(text: str, source: str, actor: Optional[str] = None) -> dict:
        """Record a fact you learned and where it came from, so decisions can cite it."""
        return svc.add_finding(text, source, actor)

    @mcp.tool()
    def why(decision_id: str) -> dict:
        """Everything a decision was (transitively) based on."""
        return svc.why(decision_id)

    @mcp.tool()
    def retract(item_id: str, reason: str = "", actor: Optional[str] = None) -> dict:
        """Mark a decision or finding wrong; returns every decision derived from it (now tainted)."""
        return svc.retract(item_id, reason, actor)

    @mcp.tool()
    def handoff_export(task_id: str, actor: Optional[str] = None) -> dict:
        """Package the context around a task (decisions, findings, artifacts) for the next session."""
        return svc.handoff_export(task_id, actor)

    @mcp.tool()
    def handoff_import(handoff_id: str, actor: Optional[str] = None) -> dict:
        """Load a handoff packet with current statuses."""
        return svc.handoff_import(handoff_id, actor)

    return mcp


def main() -> None:
    server = build_server()
    print("baton MCP server starting (stdio)", file=sys.stderr)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
