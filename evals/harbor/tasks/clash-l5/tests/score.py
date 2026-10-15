"""Run the collision checker and write Harbor's reward files."""
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
