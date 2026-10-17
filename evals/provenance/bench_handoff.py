"""Benchmark B: does the next session's briefing carry the ground-truth items of the previous session?

Deterministic: scripted sessions, known items, substring checks on the rendered briefing text.
Usage: PYTHONPATH=src python -B evals/provenance/bench_handoff.py
"""

import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import RESULTS_DIR, mean, new_store  # noqa: E402

from baton.core import decisions, handoff, provenance, sessions  # noqa: E402

NOTE_TOKEN = "resume at migrate_rollback()"
NOTE = "UNFINISHED: port the rollback path in db.py; " + NOTE_TOKEN
VERIF_TOKEN = "2 failed"
VERIF = "pytest: 41 passed, 2 failed (test_migrate_rollback, test_migrate_idempotent)"
CLASSES = ("tainted", "interface", "config_storage", "note")


def script(ws, n, long_text, n_files, seed, delay):
    rng = random.Random(seed)
    s = new_store(ws)
    t0 = 10000.0
    files = ["src/app/mod%02d.py" % i for i in range(n_files)]
    sessions.begin_session(s, "sessA", now=t0)
    sessions.set_goal(s, "sessA", "Migrate the storage layer to sqlite", now=t0)
    for i, f in enumerate(files):
        sessions.touch(s, "sessA", f, now=t0 + i)
    provenance.add_finding(s, "sessA", "orders must survive restart", "ticket-12", finding_id="FBAD", now=t0)
    provenance.add_finding(s, "sessA", "sqlite is available on all targets", "ci", finding_id="FOK", now=t0)
    truth = {}  # token -> class
    for i in range(n):
        tok = "K%03d" % i
        r = rng.random()
        kind = "interface" if r < 0.15 else ("config" if r < 0.20 else ("storage" if r < 0.25 else "note"))
        based = []
        if rng.random() < 0.12:
            based = ["FBAD"]
        elif rng.random() < 0.05:
            based = ["FOK"]
        body = "%s change %s behaviour in %s" % (tok, kind, rng.choice(files))
        if long_text:
            body += " " + "because of detailed reasoning about edge cases " * 8
        decisions.post_decision(s, "sessA", body, artifacts=[rng.choice(files)], based_on=based, kind=kind,
                                decision_id="dec_" + tok, now=t0 + 100 + i)
        truth[tok] = (kind, bool(based and based[0] == "FBAD"))
    provenance.retract(s, "FBAD", "sessA", reason="spec changed", now=t0 + 100 + n)
    classes = {}
    for tok, (kind, bad) in truth.items():
        classes[tok] = "tainted" if bad else ("interface" if kind == "interface" else
                                              ("config_storage" if kind in ("config", "storage") else "note"))
    pk = sessions.export_session_handoff(s, "sessA", note=NOTE, now=t0 + 200 + n, verification=VERIF)
    brief = sessions.briefing(s, "sessB", now=t0 + 300 + n + delay)
    return s, files, classes, pk, brief


def measure(n, long_text, n_files, seed, delay):
    ws = "prov_hand_%d_%d_%d_%d_%d" % (n, int(long_text), n_files, seed, delay)
    s, files, classes, pk, brief = script(ws, n, long_text, n_files, seed, delay)
    try:
        # which decisions did export keep, and which survive the rendered handoff text, and the whole briefing
        exported = {d["id"][4:] for d in pk["decisions"]}
        in_handoff_text = {t for t in classes if t in pk["text"]}
        in_brief = {t for t in classes if t in brief}
        res = dict(n=n, delay=delay, long=long_text, files=n_files, seed=seed,
                   brief_chars=len(brief), handoff_chars=len(pk["text"]),
                   note=NOTE_TOKEN in brief, verification=VERIF_TOKEN in brief,
                   files_kept=sum(1 for f in files if f in brief), files_total=len(files),
                   exported=len(exported), omitted_by_export=pk["omitted"])
        for c in CLASSES:
            toks = {t for t, k in classes.items() if k == c}
            res[c + "_total"] = len(toks)
            res[c + "_exported"] = len(toks & exported)
            res[c + "_in_brief"] = len(toks & in_brief)
        # priority inversions in the briefing: a lower-priority item kept while a higher one is dropped
        rank = {"tainted": 0, "interface": 1, "config_storage": 1, "note": 2}
        kept = [rank[classes[t]] for t in in_brief]
        dropped = [rank[classes[t]] for t in classes if t not in in_brief]
        res["inversions"] = int(bool(kept and dropped and max(kept) > min(dropped)))
        res["worst_dropped_class_rank"] = min(dropped) if dropped else None
        # tainted flag survives?
        res["tainted_flag_lines"] = brief.count("TAINTED") + brief.count("(tainted)")
        return res
    finally:
        s.drop()


def main():
    rows = []
    for n in (10, 50, 200):
        for long_text in (False, True):
            for n_files in (6, 30):
                for delay in (0, 36 * 3600):  # resume right away / 1.5 days later (past the 24h decision window)
                    for seed in (1, 2, 3):
                        rows.append(measure(n, long_text, n_files, seed, delay))
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(os.path.join(RESULTS_DIR, sys.argv[1] if len(sys.argv) > 1 else "handoff.json"), "w") as f:
        json.dump(rows, f, indent=1)
    print("%4s %5s %5s %4s | %5s %5s | %5s %6s | %-8s %-9s %-9s %-6s | inv  brief handoff" % (
        "N", "long", "files", "when", "note", "verif", "files", "export", "tainted", "interface", "cfg/stor", "note"))
    groups = {}
    for r in rows:
        groups.setdefault((r["n"], r["long"], r["files"], r["delay"] > 0), []).append(r)
    for (n, lg, nf, late), rs in groups.items():
        def frac(c, key):
            tot = sum(r[c + "_total"] for r in rs)
            return "%d/%d" % (sum(r[c + key] for r in rs), tot)
        print("%4d %5s %5d %s | %5s %5s | %5s %6.1f | %-8s %-9s %-9s %-6s | %d/%d %5d %5d" % (
            n, lg, nf, "late" if late else "now ", "%d/%d" % (sum(r["note"] for r in rs), len(rs)), "%d/%d" % (sum(r["verification"] for r in rs), len(rs)),
            "%.2f" % mean(r["files_kept"] / r["files_total"] for r in rs), mean(r["exported"] for r in rs),
            frac("tainted", "_in_brief"), frac("interface", "_in_brief"), frac("config_storage", "_in_brief"),
            frac("note", "_in_brief"), sum(r["inversions"] for r in rs), len(rs),
            max(r["brief_chars"] for r in rs), max(r["handoff_chars"] for r in rs)))


if __name__ == "__main__":
    main()
