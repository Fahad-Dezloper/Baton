"""Defensive reader for the host's session transcript (JSONL, mixed record types).

Observed shape (host 2.1.x): each line is a JSON object; `message.content` is either a string
(user prompt) or a list of typed blocks (`text`, `thinking`, `tool_use`, `tool_result`). The file
is written asynchronously, so the tail may be stale; every function here is best-effort and never
raises.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterator, List, Optional

TAIL_BYTES = 2_000_000
_TEST_CMD = re.compile(
    r"(pytest|unittest|\bnpm\s+(run\s+)?test|\byarn\s+test|\bpnpm\s+(run\s+)?test|go\s+test|cargo\s+test"
    r"|\bjest\b|\bvitest\b|\bmocha\b|\bmake\s+test|\btox\b)",
    re.I,
)
_FAIL = re.compile(r"(\bFAILED\b|failures=\d|errors=\d|\b\d+\s+failed\b|\bFAIL\b|Traceback|Exit code [1-9])")
_PASS = re.compile(r"(\bOK\b|\b\d+\s+passed\b|\b\d+\s+passing\b|\ball tests passed\b|^ok\s|test result: ok)", re.I | re.M)


def read_records(path: Optional[str], max_bytes: int = TAIL_BYTES) -> List[Dict[str, Any]]:
    if not path:
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            start = max(0, size - max_bytes)
            f.seek(start)
            data = f.read()
    except OSError:
        return []
    lines = data.split(b"\n")
    if start > 0 and lines:
        lines = lines[1:]  # first line is likely cut in half
    out: List[Dict[str, Any]] = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _blocks(rec: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    msg = rec.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict):
                yield b


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
    return ""


def tool_calls(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pair tool_use blocks with their tool_result by id, in order."""
    calls: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for rec in records:
        for b in _blocks(rec):
            t = b.get("type")
            if t == "tool_use" and b.get("id"):
                calls[b["id"]] = {"id": b["id"], "name": b.get("name"), "input": b.get("input") or {},
                                  "result": "", "is_error": False, "has_result": False}
                order.append(b["id"])
            elif t == "tool_result" and b.get("tool_use_id") in calls:
                c = calls[b["tool_use_id"]]
                c["result"] = _text_of(b.get("content"))
                c["is_error"] = bool(b.get("is_error"))
                c["has_result"] = True
    return [calls[i] for i in order]


def last_test_run(records: List[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    """The most recent test command and whether it passed: {command, status, summary}."""
    for call in reversed(tool_calls(records)):
        if call["name"] != "Bash" or not call["has_result"]:
            continue
        cmd = str((call["input"] or {}).get("command", ""))
        if not _TEST_CMD.search(cmd):
            continue
        text = call["result"]
        if call["is_error"] or _FAIL.search(text):
            status = "failed"
        elif _PASS.search(text):
            status = "passed"
        else:
            status = "unknown"
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return {"command": " ".join(cmd.split())[:120], "status": status,
                "summary": (lines[-1] if lines else "")[:120]}
    return None
