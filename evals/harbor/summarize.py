#!/usr/bin/env python3
"""Summarize Harbor evaluation jobs: per level and arm, how many trials were collision-free.

Usage: python3 evals/harbor/summarize.py "<glob of job dirs>" [--oneline] [--write]
Reads each trial's verifier/reward.json and verifier/check.json (and the plugin hook log).
"""
import collections
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def arm_of(job_dir):
    cfg = open(os.path.join(job_dir, "config.json")).read() if os.path.exists(os.path.join(job_dir, "config.json")) else ""
    if "BatonClashPlugin" in cfg:
        return "plugin"
    if "BatonClashBaseline" in cfg:
        return "baseline"
    return "plugin" if "plugin" in os.path.basename(job_dir) else "baseline"


def trials(job_dir):
    out = []
    for t in sorted(glob.glob(os.path.join(job_dir, "*__*"))):
        if not os.path.isdir(t):
            continue
        m = re.search(r"clash-(l\d+)", os.path.basename(t))
        reward = load(os.path.join(t, "verifier", "reward.json"))
        check = load(os.path.join(t, "verifier", "check.json")) or {}
        warnings = errors = 0
        log = os.path.join(t, "agent", "baton-hooks.log")
        if os.path.exists(log):
            for line in open(log):
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("error"):
                    errors += 1
                ctx = ((r.get("output") or {}).get("hookSpecificOutput") or {}).get("additionalContext", "")
                if "Possible collision" in ctx or "same goal" in ctx:
                    warnings += 1
        out.append({
            "level": (m.group(1).upper() if m else "?"),
            "ok": bool(reward and reward.get("clash_free") == 1.0),
            "scored": reward is not None,
            "failed_checks": (reward or {}).get("checks_failed"),
            "types": [c.get("type") for c in check.get("clashes", [])],
            "warnings": warnings,
            "hook_errors": errors,
        })
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    oneline = "--oneline" in sys.argv
    pattern = args[0] if args else os.path.join(HERE, "jobs", "eval-*")
    rows = collections.defaultdict(list)
    for job in sorted(glob.glob(pattern)):
        if not os.path.isdir(job):
            continue
        arm = arm_of(job)
        for t in trials(job):
            rows[(t["level"], arm)].append(t)
    if not rows:
        print("no trials found for", pattern)
        return

    if oneline:
        for (lvl, arm), ts in sorted(rows.items()):
            ok = sum(1 for t in ts if t["ok"])
            print("    %s %-8s clash-free %d/%d" % (lvl, arm, ok, len(ts)))
        return

    levels = sorted({k[0] for k in rows})
    lines = ["| Level | Arm | Trials | Clash-free | Avg failed checks | Collision warnings delivered | Most common problems |",
             "|---|---|---|---|---|---|---|"]
    for lvl in levels:
        for arm in ("baseline", "plugin"):
            ts = rows.get((lvl, arm))
            if not ts:
                continue
            ok = sum(1 for t in ts if t["ok"])
            fc = [t["failed_checks"] for t in ts if t["failed_checks"] is not None]
            avg = "%.1f" % (sum(fc) / len(fc)) if fc else "-"
            types = collections.Counter(x for t in ts for x in t["types"])
            top = ", ".join("%s x%d" % kv for kv in types.most_common(3)) or "none"
            warn = str(sum(t["warnings"] for t in ts)) if arm == "plugin" else "n/a"
            lines.append("| %s | %s | %d | %d/%d | %s | %s | %s |" % (lvl, arm, len(ts), ok, len(ts), avg, warn, top))
    out = "\n".join(lines)
    print(out)
    errs = sum(t["hook_errors"] for ts in rows.values() for t in ts)
    unscored = sum(1 for ts in rows.values() for t in ts if not t["scored"])
    print("\nunscored trials: %d | plugin hook errors: %d" % (unscored, errs))
    if "--write" in sys.argv:
        os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
        with open(os.path.join(HERE, "results", "SUMMARY.md"), "w") as f:
            f.write("# Evaluation summary\n\n" + out + "\n")
        print("wrote evals/harbor/results/SUMMARY.md")


if __name__ == "__main__":
    main()
