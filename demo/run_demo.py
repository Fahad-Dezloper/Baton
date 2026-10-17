#!/usr/bin/env python3
"""Scripted two-session scenario against a live FalkorDB. No model calls, no API key.

It drives the same hook handlers the Claude Code plugin uses, with the same payload shapes, so what
it prints is what a real session would be told. Afterwards the graph stays in FalkorDB (workspace
"demo") so you can open the Browser at http://localhost:3000 and run demo/queries.cypher.

    docker compose up -d
    .venv/bin/python demo/run_demo.py
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from baton.core import decisions, provenance  # noqa: E402
from baton.graph.client import Store  # noqa: E402
from baton.hooks.config import Config  # noqa: E402
from baton.hooks.events import HANDLERS  # noqa: E402

WORKSPACE = "demo"
A, B, C = "sess-A-storage", "sess-B-endpoint", "sess-C-next-day"


def say(title):
    print("\n=== %s ===" % title)


def show(who, out):
    text = ((out or {}).get("hookSpecificOutput") or {}).get("additionalContext") or "(nothing to say)"
    print("[to %s]\n%s" % (who, text))


def main():
    project = tempfile.mkdtemp(prefix="baton_demo_")
    shutil.copytree(os.path.join(ROOT, "evals", "clash", "fixture"), os.path.join(project, "p"))
    project = os.path.join(project, "p")
    os.environ["CLAUDE_PROJECT_DIR"] = project
    store = Store(WORKSPACE)
    store.drop()
    store = Store(WORKSPACE)
    store.bootstrap()
    cfg = Config()
    db_path = os.path.join(project, "shop", "db.py")
    api_path = os.path.join(project, "shop", "api.py")
    original = open(db_path).read()
    t = [1_000_000.0]

    def fire(event, session, now_add=1.0, **payload):
        t[0] += now_add
        payload.update({"session_id": session, "cwd": project})
        return HANDLERS[event](store, payload, cfg, now=t[0])

    say("1. Two sessions start on the same checkout")
    for s in (A, B):
        fire("session-start", s)
    fire("prompt", A, prompt="Ticket 12: make get_order take an include_cancelled flag and keep orders in sqlite.")
    fire("prompt", B, prompt="Ticket 15: add an order lookup endpoint in shop/api.py that uses db.get_order.")
    print("session A: sqlite + get_order signature; session B: new endpoint on top of get_order")

    say("2. Session A edits shop/db.py (signature change + new storage engine)")
    new = original.replace("def get_order(order_id):", "def get_order(order_id, include_cancelled=False):")
    new = "import sqlite3\n" + new
    edit = {"tool_name": "Write", "tool_input": {"file_path": db_path, "content": new},
            "tool_response": {"type": "update", "originalFile": original, "content": new}}
    show(A, fire("pre-tool", A, **edit))
    fire("post-tool", A, **edit)
    print("recorded without anyone typing a command:")
    for d in decisions.check_conflicts(store, B, ["shop/db.py"], now=t[0])["decisions"]:
        print("  - [%s] %s" % (d["kind"], d["text"]))

    say("3. Session B is about to edit a different file that imports db")
    b_edit = {"tool_name": "Edit", "tool_input": {"file_path": api_path, "old_string": "x", "new_string": "y"},
              "tool_response": {"originalFile": open(api_path).read()}}
    show(B, fire("pre-tool", B, **b_edit))

    say("4. Session B goes for the same file as A")
    b_same = {"tool_name": "Edit", "tool_input": {"file_path": db_path, "old_string": "x", "new_string": "y"},
              "tool_response": {"originalFile": new}}
    show(B, fire("pre-tool", B, **b_same))

    say("5. Session A stops; a new session picks it up the next day")
    fire("stop", A, last_assistant_message="get_order now takes include_cancelled; db.py imports sqlite3 but "
                                          "save_order still writes the dict. Next: migrate save_order.")
    fire("session-end", A)
    show(C, fire("session-start", C, now_add=3600))

    say("6. Provenance: a bad finding is retracted and its blast radius is found")
    f = provenance.add_finding(store, A, "Orders must survive restarts (per requirements v1)", source="requirements v1",
                               now=t[0])
    d1 = decisions.post_decision(store, A, "use sqlite for order storage", artifacts=["shop/db.py"],
                                 based_on=[f["id"]], kind="storage", now=t[0])
    d2 = decisions.post_decision(store, B, "endpoint reads through db.get_order, no cache",
                                 artifacts=["shop/api.py"], based_on=[d1["id"]], kind="interface", now=t[0])
    res = provenance.retract(store, f["id"], B, reason="requirements v2 dropped the durability need", now=t[0])
    print("retracted finding %s -> tainted %d decision(s):" % (f["id"], len(res["tainted"])))
    for d in res["tainted"]:
        print("  - %s (%s)" % (d["text"], d["id"]))
    print("why(%s): %s" % (d2["id"], [x["text"] for x in provenance.why(store, d2["id"])["findings"]]))

    print("\nGraph left in FalkorDB as workspace '%s' (graph 'baton_%s')." % (WORKSPACE, WORKSPACE))
    print("Open http://localhost:3000 and run the queries in demo/queries.cypher.")


if __name__ == "__main__":
    main()
