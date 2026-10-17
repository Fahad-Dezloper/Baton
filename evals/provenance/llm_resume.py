"""Benchmark C (optional): same unfinished task, fresh session, with vs without the handoff briefing.

Uses `claude -p --model claude-haiku-5-5` (subscription). 4 runs per arm = 8 total. Deterministic checker.
Usage: PYTHONPATH=src python -B evals/provenance/llm_resume.py <scratch_dir>
"""

import json
import os
import ast
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import RESULTS_DIR, new_store  # noqa: E402

from baton.core import decisions, provenance, sessions  # noqa: E402

DB_PY = '''"""Storage layer, mid-migration to sqlite."""
import sqlite3


def connect(path):
    return sqlite3.connect(path)


def migrate(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, total REAL)")
    conn.execute("CREATE TABLE IF NOT EXISTS _migrations (version INTEGER)")
    conn.execute("INSERT INTO _migrations VALUES (2)")
    conn.commit()


def migrate_rollback(conn):
    raise NotImplementedError
'''
PROMPT = "Finish the unfinished work in this repository. Edit files directly, keep it short, then stop."


def make_briefing():
    s = new_store("prov_llm_resume")
    try:
        t0 = 50000.0
        sessions.begin_session(s, "sessA", now=t0)
        sessions.set_goal(s, "sessA", "Migrate the storage layer to sqlite", now=t0)
        sessions.touch(s, "sessA", "db.py", now=t0 + 1)
        decisions.post_decision(
            s, "sessA", "Rollback must copy orders into table _orders_bak before dropping anything; the name is fixed by the ops runbook",
            artifacts=["db.py"], kind="interface", now=t0 + 2)
        decisions.post_decision(s, "sessA", "migrate() keeps version rows in _migrations", artifacts=["db.py"], kind="storage", now=t0 + 3)
        sessions.export_session_handoff(
            s, "sessA", note="UNFINISHED: implement migrate_rollback() in db.py, then stop", now=t0 + 10,
            verification="pytest: 3 passed, 1 failed (test_rollback)")
        return sessions.briefing(s, "sessB", now=t0 + 60)
    finally:
        s.drop()


def check(path):
    src = open(os.path.join(path, "db.py")).read()
    try:
        ast.parse(src)
        ok_syntax = True
    except Exception:
        ok_syntax = False
    done = "NotImplementedError" not in src.split("def migrate_rollback", 1)[-1]
    return dict(syntax=ok_syntax, implemented=done, uses_runbook_table="_orders_bak" in src,
                passed=ok_syntax and done and "_orders_bak" in src)


def run_arm(scratch, arm, i, briefing):
    d = os.path.join(scratch, "%s_%d" % (arm, i))
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "db.py"), "w") as f:
        f.write(DB_PY)
    prompt = (briefing + "\n\n" + PROMPT) if arm == "with" else PROMPT
    p = subprocess.run(["claude", "-p", prompt, "--model", "claude-haiku-5-5", "--permission-mode", "acceptEdits",
                        "--allowedTools", "Read", "Edit", "Write"], cwd=d, capture_output=True, text=True, timeout=280)
    r = check(d)
    r.update(arm=arm, run=i, rc=p.returncode)
    return r


def recheck(scratch):
    """Re-score already-produced outputs (used after fixing the checker; no model calls)."""
    rows = []
    for i in range(4):
        for arm in ("without", "with"):
            r = check(os.path.join(scratch, "%s_%d" % (arm, i)))
            r.update(arm=arm, run=i)
            rows.append(r)
    return rows


def main():
    scratch = sys.argv[1]
    if len(sys.argv) > 2 and sys.argv[2] == "recheck":
        rows = recheck(scratch)
        with open(os.path.join(RESULTS_DIR, "llm_resume.json"), "w") as f:
            json.dump(dict(briefing=make_briefing(), rows=rows), f, indent=1)
        for arm in ("without", "with"):
            rs = [r for r in rows if r["arm"] == arm]
            print(arm, sum(r["passed"] for r in rs), "/", len(rs), rs)
        return
    briefing = make_briefing()
    rows = []
    for i in range(4):
        for arm in ("without", "with"):
            try:
                rows.append(run_arm(scratch, arm, i, briefing))
            except Exception as e:  # report, do not hide
                rows.append(dict(arm=arm, run=i, error=repr(e)[:200], passed=False))
            print(rows[-1], flush=True)
    with open(os.path.join(RESULTS_DIR, "llm_resume.json"), "w") as f:
        json.dump(dict(briefing=briefing, rows=rows), f, indent=1)
    for arm in ("without", "with"):
        rs = [r for r in rows if r["arm"] == arm]
        print(arm, sum(r["passed"] for r in rs), "/", len(rs))


if __name__ == "__main__":
    main()
