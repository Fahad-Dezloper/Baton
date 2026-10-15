"""Deterministic extraction of public signatures and imports from source text (no parsing deps)."""

from __future__ import annotations

import os
import re
import sys
from typing import Dict, List, Set, Tuple

_PY = [
    re.compile(r"^[ \t]*(?:async\s+)?def\s+([A-Za-z]\w*)\s*\(([^)]*)\)", re.M),
    re.compile(r"^[ \t]*class\s+([A-Za-z]\w*)\s*(?:\(([^)]*)\))?", re.M),
]
_JS = [
    re.compile(r"^[ \t]*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(([^)]*)\)", re.M),
    re.compile(r"^[ \t]*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>", re.M),
    re.compile(r"^[ \t]*(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)", re.M),
]
_GO = [re.compile(r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z]\w*)\s*\(([^)]*)\)", re.M)]
_RS = [re.compile(r"^[ \t]*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z]\w*)\s*(?:<[^>]*>)?\s*\(([^)]*)\)", re.M)]

_BY_EXT = {
    ".py": _PY, ".js": _JS, ".jsx": _JS, ".ts": _JS, ".tsx": _JS, ".mjs": _JS,
    ".go": _GO, ".rs": _RS,
}

_PY_IMPORT = [
    re.compile(r"^[ \t]*import\s+([\w.]+(?:\s*,\s*[\w.]+)*)", re.M),
    re.compile(r"^[ \t]*from\s+([\w.]+)\s+import\s", re.M),
]
_JS_IMPORT = [
    re.compile(r"""^[ \t]*import\s+(?:[^'"\n]*\sfrom\s+)?['"]([^'"]+)['"]""", re.M),
    re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)"""),
]

STORAGE_MODULES = {
    "sqlite3", "psycopg2", "psycopg", "pymongo", "redis", "sqlalchemy", "mysql", "peewee", "shelve",
    "asyncpg", "aiosqlite", "motor", "boto3",
    "better-sqlite3", "sqlite3", "pg", "mongodb", "mongoose", "ioredis", "prisma", "@prisma/client",
    "typeorm", "knex", "sequelize", "redis",
}


def _norm(params: str) -> str:
    return " ".join((params or "").split())


def signatures(text: str, path: str) -> Dict[str, str]:
    """Public name -> 'name(params)'. Empty for unsupported file types."""
    pats = _BY_EXT.get(os.path.splitext(path)[1].lower())
    if not pats or not text:
        return {}
    out: Dict[str, str] = {}
    for pat in pats:
        for m in pat.finditer(text):
            name = m.group(1)
            if name.startswith("_"):
                continue
            params = m.group(2) if m.lastindex and m.lastindex >= 2 else None
            sig = "%s(%s)" % (name, _norm(params)) if params is not None else name
            out.setdefault(name, sig)
    return out


def diff_signatures(old: Dict[str, str], new: Dict[str, str]) -> Tuple[List[Tuple[str, str]], List[str], List[str]]:
    """Returns (changed [(old_sig, new_sig)], added [sig], removed [sig])."""
    changed = [(old[n], new[n]) for n in new if n in old and old[n] != new[n]]
    added = [new[n] for n in new if n not in old]
    removed = [old[n] for n in old if n not in new]
    return changed, added, removed


def imports(text: str, path: str) -> Set[str]:
    """Top-level, non-relative module names imported by the file."""
    ext = os.path.splitext(path)[1].lower()
    found: Set[str] = set()
    if ext == ".py":
        for pat in _PY_IMPORT:
            for m in pat.finditer(text or ""):
                for part in m.group(1).split(","):
                    mod = part.strip().split(".")[0]
                    if mod:
                        found.add(mod)
        std = getattr(sys, "stdlib_module_names", set())
        return {m for m in found if m in STORAGE_MODULES or m not in std}
    if ext in (".js", ".jsx", ".ts", ".tsx", ".mjs"):
        for pat in _JS_IMPORT:
            for m in pat.finditer(text or ""):
                mod = m.group(1)
                if mod.startswith(".") or mod.startswith("node:"):
                    continue
                parts = mod.split("/")
                found.add("/".join(parts[:2]) if mod.startswith("@") else parts[0])
        return found
    return set()
