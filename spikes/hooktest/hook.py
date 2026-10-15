#!/usr/bin/env python3
"""Probe hook: logs raw stdin JSON per event and returns a few scripted responses.

Usage in settings: python3 hook.py <event_label>
Log: ./hook-log.jsonl next to this file.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "hook-log.jsonl")


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {"_unparsed": raw[:500]}
    with open(LOG, "a") as f:
        f.write(json.dumps({"label": label, "ts": time.time(), "input": data}) + "\n")

    if label == "session_start":
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "BATON-PROBE: the secret project codename is ORCHID-7. "
                                     "Mention it if asked what the codename is.",
            }
        }))
    elif label == "pre_tool":
        text = json.dumps(data.get("tool_input", {}))
        if "forbidden" in text:
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "BATON-PROBE: another session holds a lease on this file.",
                }
            }))
        elif "needs-ask" in text:
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": "BATON-PROBE: open decision touches this file.",
                }
            }))
    sys.exit(0)


if __name__ == "__main__":
    main()
