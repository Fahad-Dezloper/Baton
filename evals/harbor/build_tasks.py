#!/usr/bin/env python3
"""Generate the Harbor tasks (one per clash level) from the single source of truth, evals/clash/tasks.json.

Usage: python3 evals/harbor/build_tasks.py
Writes evals/harbor/tasks/clash-l1 ... clash-l5.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "clash", "tasks.json")
OUT = os.path.join(HERE, "tasks")

TASK_TOML = """schema_version = "1.4"
artifacts = []

[metadata]
level = "{level}"
description = "{name}"

[verifier]
timeout_sec = 180.0
collect = []

[verifier.env]

[agent]
timeout_sec = 1200.0

[environment]
network_mode = "public"
build_timeout_sec = 1800.0
os = "linux"
mcp_servers = []

[environment.env]

[solution.env]
"""

INSTRUCTION = """# Parallel tickets ({level}): {name}

Several engineers pick up the tickets below at the same moment, each working in the same
checkout of the `shop` package at `/app/project`. This task is scored on whether their combined
result is free of collisions (lost updates, broken imports, mismatched contracts, duplicated or
contradictory work).

```json
{payload}
```
"""

TEST_SH = """#!/bin/bash
# Scores the shared checkout with the same checker used by the local harness.
mkdir -p /logs/verifier
python3 -B /tests/score.py {level}
"""

SCORE_PY = '''"""Run the collision checker and write Harbor's reward files."""
import json
import subprocess
import sys

level = sys.argv[1]
proc = subprocess.run(
    [sys.executable, "-B", "/opt/clash/check.py", level, "/app/project"],
    capture_output=True, text=True, timeout=150,
)
try:
    res = json.loads(proc.stdout)
except ValueError:
    res = {"clash_free": False, "clash_count": 99, "checks": {}, "clashes": [{"type": "checker_error",
           "detail": (proc.stderr or proc.stdout)[-300:]}]}

checks = res.get("checks", {})
passed = sum(1 for v in checks.values() if v)
total = max(1, len(checks))
reward = {
    "clash_free": 1.0 if res.get("clash_free") else 0.0,
    "checks_failed": float(res.get("clash_count", 0)),
    "checks_passed_fraction": round(passed / total, 4),
}
with open("/logs/verifier/reward.json", "w") as f:
    json.dump(reward, f)
with open("/logs/verifier/check.json", "w") as f:
    json.dump(res, f, indent=2)
print(json.dumps(reward))
'''


def main():
    with open(SRC) as f:
        spec = json.load(f)
    for level, info in spec["levels"].items():
        d = os.path.join(OUT, "clash-" + level.lower())
        for sub in ("environment", "tests"):
            os.makedirs(os.path.join(d, sub), exist_ok=True)
        payload = json.dumps({"level": level, "workers": info["agents"]}, indent=2)
        files = {
            "task.toml": TASK_TOML.format(level=level, name=info["name"].replace('"', "'")),
            "instruction.md": INSTRUCTION.format(level=level, name=info["name"], payload=payload),
            "environment/Dockerfile": "FROM baton-eval:latest\n",
            "tests/test.sh": TEST_SH.format(level=level),
            "tests/score.py": SCORE_PY,
        }
        for rel, content in files.items():
            with open(os.path.join(d, rel), "w") as f:
                f.write(content)
        os.chmod(os.path.join(d, "tests", "test.sh"), 0o755)
        print("wrote", os.path.relpath(d, HERE))


if __name__ == "__main__":
    main()
