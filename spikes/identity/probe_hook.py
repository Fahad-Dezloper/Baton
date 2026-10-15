"""Probe hook: dump stdin keys, env keys and the parent process chain."""
import json
import os
import subprocess
import sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dump-hook-%s.json" % sys.argv[1])


def chain():
    out, pid = [], os.getpid()
    for _ in range(8):
        line = subprocess.run(
            ["ps", "-o", "pid=,ppid=,comm=", "-p", str(pid)], capture_output=True, text=True
        ).stdout.strip()
        if not line:
            break
        parts = line.split(None, 2)
        out.append(parts)
        pid = int(parts[1])
        if pid <= 1:
            break
    return out


raw = sys.stdin.read()
try:
    data = json.loads(raw)
except Exception:
    data = {}
with open(OUT, "w") as f:
    json.dump(
        {
            "pid": os.getpid(),
            "chain": chain(),
            "stdin_session_id": data.get("session_id"),
            "env_interesting": {
                k: (v[:60] if len(v) > 60 else v)
                for k, v in os.environ.items()
                if any(s in k.upper() for s in ("CLAUDE", "SESSION", "ANTHROPIC", "MCP", "AGENT", "PROJECT"))
                and "KEY" not in k.upper() and "TOKEN" not in k.upper() and "SECRET" not in k.upper()
            },
        },
        f,
        indent=2,
    )
sys.exit(0)
