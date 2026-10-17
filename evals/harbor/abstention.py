#!/usr/bin/env python3
"""Abstention analysis from session transcripts: which sessions finished without changing any file?

Usage: python3 evals/harbor/abstention.py <jobs_dir> <label>=<glob> ...
   e.g. abstention.py evals/harbor/jobs baseline='eval-baseline-l*-k5' v3='eval3-plugin-l*-k5'

A session "wrote" if its transcript (agent/sessions/projects/*/<session_id>.jsonl) has a Write,
Edit or MultiEdit tool call that did not return an error, or a Bash call whose command looks like
a file mutation (output redirection to a file, tee, sed -i, mv, cp, git apply/checkout/restore,
python open(..., 'w')). Sessions are mapped to tickets through agent/worker-<key>.json session_id.
Prints counts per label, overall, outside L5 (where standing down is the designed behaviour) and
per level, plus the list of abstaining sessions.
"""
import collections
import glob
import json
import os
import re
import sys

MUT = re.compile(r"(>>?\s*[\w./\"'$-]|\btee\b|sed\s+-i|\bmv\s|\bcp\s|git\s+(apply|checkout|restore|stash)|open\([^)]*['\"][wa]b?['\"])")
SKIP_REDIR = re.compile(r"(2>&1|2>/dev/null|>/dev/null|&>/dev/null|1>&2)")


def bash_mutates(cmd):
    cmd = SKIP_REDIR.sub(" ", cmd)
    return bool(MUT.search(cmd))


def session_wrote(path):
    errs, uses = set(), []
    try:
        lines = open(path).read().splitlines()
    except OSError:
        return None
    for ln in lines:
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        c = (d.get("message") or {}).get("content")
        if not isinstance(c, list):
            continue
        for b in c:
            if b.get("type") == "tool_use":
                uses.append(b)
            elif b.get("type") == "tool_result" and b.get("is_error"):
                errs.add(b.get("tool_use_id"))
    for b in uses:
        if b["name"] in ("Write", "Edit", "MultiEdit") and b["id"] not in errs:
            return True
        if b["name"] == "Bash" and bash_mutates((b.get("input") or {}).get("command", "")):
            return True
    return False


def trial_sessions(trial):
    out = []
    for wf in sorted(glob.glob(os.path.join(trial, "agent", "worker-*.json"))):
        key = os.path.basename(wf)[7:-5]
        try:
            sid = json.load(open(wf)).get("session_id")
        except ValueError:
            sid = None
        if not sid:
            out.append((key, None))
            continue
        hits = glob.glob(os.path.join(trial, "agent", "sessions", "projects", "*", sid + ".jsonl"))
        out.append((key, session_wrote(hits[0]) if hits else None))
    return out


def main():
    jobs = sys.argv[1]
    groups = [a.split("=", 1) for a in sys.argv[2:] if "=" in a]
    for label, pat in groups:
        rows = collections.defaultdict(lambda: [0, 0])  # level -> [sessions, abstained]
        unknown, detail = 0, []
        for job in sorted(glob.glob(os.path.join(jobs, pat))):
            if not os.path.isdir(job):
                continue
            for t in sorted(glob.glob(os.path.join(job, "*__*"))):
                m = re.search(r"clash-(l\d+)", os.path.basename(t))
                lvl = m.group(1).upper() if m else "?"
                for key, wrote in trial_sessions(t):
                    if wrote is None:
                        unknown += 1
                        continue
                    rows[lvl][0] += 1
                    if not wrote:
                        rows[lvl][1] += 1
                        detail.append("%s/%s/%s" % (os.path.basename(job), os.path.basename(t)[-7:], key))
        tot = sum(v[0] for v in rows.values()); ab = sum(v[1] for v in rows.values())
        o5 = [v for k, v in rows.items() if k != "L5"]
        ot = sum(v[0] for v in o5); oa = sum(v[1] for v in o5)
        print("== %s: abstained %d/%d (%.1f%%); outside L5 %d/%d (%.1f%%); transcripts missing: %d"
              % (label, ab, tot, 100.0 * ab / max(tot, 1), oa, ot, 100.0 * oa / max(ot, 1), unknown))
        print("   per level: " + ", ".join("%s %d/%d" % (k, v[1], v[0]) for k, v in sorted(rows.items(), key=lambda kv: int(kv[0][1:]) if kv[0][1:].isdigit() else 99)))
        if "-v" in sys.argv:
            print("   abstaining: " + ", ".join(detail))


if __name__ == "__main__":
    main()
