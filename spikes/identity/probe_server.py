"""Probe MCP server: on startup, dump env keys and the parent process chain to a file."""
import json
import os
import subprocess
import sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dump-server.json")


def chain():
    out, pid = [], os.getpid()
    for _ in range(8):
        try:
            line = subprocess.run(
                ["ps", "-o", "pid=,ppid=,comm=", "-p", str(pid)], capture_output=True, text=True
            ).stdout.strip()
        except Exception:
            break
        if not line:
            break
        parts = line.split(None, 2)
        out.append(parts)
        pid = int(parts[1])
        if pid <= 1:
            break
    return out


with open(OUT, "w") as f:
    json.dump(
        {
            "pid": os.getpid(),
            "chain": chain(),
            "env_interesting": {
                k: (v[:60] if len(v) > 60 else v)
                for k, v in os.environ.items()
                if any(s in k.upper() for s in ("CLAUDE", "SESSION", "ANTHROPIC", "MCP", "AGENT", "PROJECT"))
                and "KEY" not in k.upper() and "TOKEN" not in k.upper() and "SECRET" not in k.upper()
            },
            "env_key_count": len(os.environ),
        },
        f,
        indent=2,
    )

from mcp.server.mcpserver import MCPServer  # noqa: E402

m = MCPServer("probe")


@m.tool()
def noop() -> dict:
    """no-op"""
    return {"ok": True}


m.run(transport="stdio")
