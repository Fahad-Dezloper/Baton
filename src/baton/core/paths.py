"""Artifact path normalization so the same file always maps to one node."""

from __future__ import annotations

import posixpath
from typing import Iterable, List


def normalize_path(path: str) -> str:
    p = path.strip().replace("\\", "/")
    p = posixpath.normpath(p)
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/") if not p.startswith("..") else p


def normalize_paths(paths: Iterable[str]) -> List[str]:
    seen = []
    for p in paths:
        n = normalize_path(p)
        if n and n != "." and n not in seen:
            seen.append(n)
    return seen
