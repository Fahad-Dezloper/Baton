#!/usr/bin/env python3
"""Token / turn / time usage per trial, by arm and level (from Harbor result.json files).

Usage: python3 evals/harbor/usage.py "<job dir glob>" ["<glob>" ...]
Arm is read from the job config. Costs are list-price estimates (subscription is not billed per token).
"""
import collections
import glob
import json
import os
import statistics
import sys
from datetime import datetime


def load(p):
    try:
        return json.load(open(p))
    except (OSError, ValueError):
        return None


def arm_of(job):
    cfg = open(os.path.join(job, "config.json")).read() if os.path.exists(os.path.join(job, "config.json")) else ""
    return "plugin" if "BatonClashPlugin" in cfg else "baseline"


def secs(a, b):
    f = "%Y-%m-%dT%H:%M:%S.%fZ"
    try:
        return (datetime.strptime(b, f) - datetime.strptime(a, f)).total_seconds()
    except (TypeError, ValueError):
        return None


def rows(globs):
    out = []
    for g in globs:
        for job in sorted(glob.glob(g)):
            if not os.path.isdir(job):
                continue
            arm = arm_of(job)
            for t in glob.glob(os.path.join(job, "*__*")):
                r = load(os.path.join(t, "result.json"))
                if not r or not r.get("agent_result"):
                    continue
                ar = r["agent_result"]
                md = ar.get("metadata") or {}
                ws = md.get("workers") or []
                ex = r.get("agent_execution") or {}
                out.append({
                    "arm": arm, "level": (md.get("level") or "?"),
                    "input": ar.get("n_input_tokens") or 0, "cache": ar.get("n_cache_tokens") or 0,
                    "output": ar.get("n_output_tokens") or 0, "cost": ar.get("cost_usd") or 0.0,
                    "turns": sum(w.get("turns") or 0 for w in ws), "sessions": len(ws),
                    "wall": secs(ex.get("started_at"), ex.get("finished_at")),
                })
    return out


def main():
    data = rows(sys.argv[1:])
    by = collections.defaultdict(list)
    for d in data:
        by[(d["level"], d["arm"])].append(d)
    print("| Level | Arm | Trials | Output tokens | Cache-read tokens | Turns | Wall s | Est. cost $ |")
    print("|---|---|---|---|---|---|---|---|")
    for (lv, arm), ds in sorted(by.items(), key=lambda kv: (int(kv[0][0][1:]) if kv[0][0][1:].isdigit() else 99, kv[0][1])):
        m = lambda k: statistics.mean(x[k] for x in ds if x[k] is not None)
        print("| %s | %s | %d | %.0f | %.0f | %.1f | %.0f | %.4f |" % (lv, arm, len(ds), m("output"), m("cache"), m("turns"), m("wall"), m("cost")))
    for arm in ("baseline", "plugin"):
        ds = [d for d in data if d["arm"] == arm]
        if ds:
            print("\nALL %s: n=%d output/trial %.0f, cache/trial %.0f, turns/trial %.1f, wall %.0fs, cost %.4f" % (
                arm, len(ds), statistics.mean(d["output"] for d in ds), statistics.mean(d["cache"] for d in ds),
                statistics.mean(d["turns"] for d in ds), statistics.mean(d["wall"] or 0 for d in ds),
                statistics.mean(d["cost"] for d in ds)))


if __name__ == "__main__":
    main()
