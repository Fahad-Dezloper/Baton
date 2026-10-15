"""Turn a file change into zero or more decisions others should know about (deterministic)."""

from __future__ import annotations

import hashlib
import os
import re
from typing import Dict, List, Optional, Set

from baton.capture.signatures import STORAGE_MODULES, diff_signatures, imports, signatures

MAX_DECISIONS_PER_EDIT = 3
MAX_BYTES = 512 * 1024

_CONFIG_EXT = {".json", ".yaml", ".yml", ".toml", ".ini", ".env", ".cfg", ".conf"}
_CONFIG_NAMES = ("config", "settings", "constants", "env")
_KEY = re.compile(r"""^\s*["']?([A-Za-z_][\w.\-]*)["']?\s*[:=]""")
_TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)(/|$)|(^|/)test_[^/]*$|[._]test\.[a-z]+$|[._]spec\.[a-z]+$")


def is_test_path(path: str) -> bool:
    return bool(_TEST_PATH.search(path.replace("\\", "/")))


def is_config_path(path: str) -> bool:
    base = os.path.basename(path).lower()
    stem, ext = os.path.splitext(base)
    return ext in _CONFIG_EXT or any(stem.startswith(n) or stem.endswith(n) for n in _CONFIG_NAMES)


def decision_id(actor: str, path: str, kind: str) -> str:
    return "dec_auto_" + hashlib.sha1(("%s|%s|%s" % (actor, path, kind)).encode()).hexdigest()[:12]


def _changed_keys(old: str, new: str) -> List[str]:
    old_lines: Set[str] = set(old.splitlines())
    new_lines: Set[str] = set(new.splitlines())
    keys: List[str] = []
    for line in list(new_lines - old_lines) + list(old_lines - new_lines):
        m = _KEY.match(line)
        if m and m.group(1) not in keys:
            keys.append(m.group(1))
    return keys


def _clip(items: List[str], n: int) -> str:
    shown = items[:n]
    more = len(items) - len(shown)
    return ", ".join(shown) + (" (+%d more)" % more if more > 0 else "")


def derive_decisions(path: str, old_text: Optional[str], new_text: Optional[str]) -> List[Dict[str, str]]:
    """Each result: {"kind", "text"}. `old_text` is None for a newly created file."""
    if new_text is None or is_test_path(path):
        return []
    if len(new_text) > MAX_BYTES or (old_text is not None and len(old_text) > MAX_BYTES):
        return []
    if old_text is not None and old_text == new_text:
        return []
    out: List[Dict[str, str]] = []

    new_sigs = signatures(new_text, path)
    old_sigs = signatures(old_text or "", path)
    if old_text is None:
        if new_sigs:
            out.append({"kind": "interface",
                        "text": "new module %s exposes: %s" % (path, _clip(sorted(new_sigs.values()), 6))})
    else:
        changed, added, removed = diff_signatures(old_sigs, new_sigs)
        parts: List[str] = []
        if changed:
            parts.append("signature changed: " + _clip(["%s -> %s" % c for c in changed], 3))
        if removed:
            parts.append("removed: " + _clip(removed, 4))
        if added:
            parts.append("added: " + _clip(added, 4))
        if parts:
            out.append({"kind": "interface", "text": "interface change in %s; %s" % (path, "; ".join(parts))})

    if is_config_path(path) and old_text is not None:
        keys = _changed_keys(old_text, new_text)
        if keys:
            out.append({"kind": "config", "text": "config change in %s; keys: %s" % (path, _clip(keys, 8))})

    added_mods = sorted(imports(new_text, path) - imports(old_text or "", path))
    if added_mods:
        storage = [m for m in added_mods if m in STORAGE_MODULES]
        if storage:
            out.append({"kind": "storage", "text": "%s now uses %s" % (path, _clip(storage, 4))})
        other = [m for m in added_mods if m not in STORAGE_MODULES]
        if other:
            out.append({"kind": "other", "text": "%s added dependency: %s" % (path, _clip(other, 4))})

    return out[:MAX_DECISIONS_PER_EDIT]


def new_text_for_edit(tool_name: str, tool_input: Dict, tool_response: Dict, old_text: Optional[str]) -> Optional[str]:
    """Reconstruct the file's new content from a post-edit payload, or None if not possible."""
    if tool_name == "Write":
        content = tool_response.get("content", tool_input.get("content"))
        return content if isinstance(content, str) else None
    if old_text is None:
        return None
    if tool_name == "Edit":
        o, n = tool_input.get("old_string"), tool_input.get("new_string")
        if not isinstance(o, str) or not isinstance(n, str):
            return None
        return old_text.replace(o, n) if tool_input.get("replace_all") else old_text.replace(o, n, 1)
    if tool_name == "MultiEdit":
        text = old_text
        for e in tool_input.get("edits") or []:
            o, n = e.get("old_string"), e.get("new_string")
            if not isinstance(o, str) or not isinstance(n, str):
                return None
            text = text.replace(o, n) if e.get("replace_all") else text.replace(o, n, 1)
        return text
    return None
