"""`baton gc [--days N] [--workspace W]`: drop finished sessions and old handoffs so a graph does not grow forever."""

from __future__ import annotations

import os
import sys
import time
from typing import List, Optional


def collect(store, days: float = 7.0, now: Optional[float] = None) -> dict:
    cut = (time.time() if now is None else now) - days * 86400
    out = {}
    for name, q in (
        ("sessions", "MATCH (t:Task) WHERE t.status = 'done' AND coalesce(t.done_at, 0) < $c "
                     "AND t.id STARTS WITH 'sess_' WITH t, count(t) AS n DETACH DELETE t RETURN sum(n)"),
        ("handoffs", "MATCH (h:Handoff) WHERE coalesce(h.created_at, 0) < $c "
                     "WITH h, count(h) AS n DETACH DELETE h RETURN sum(n)"),
        ("artifacts", "MATCH (a:Artifact) WHERE NOT (a)--() WITH a, count(a) AS n DELETE a RETURN sum(n)"),
    ):
        rows = store.rows(q, {"c": cut})
        out[name] = int(rows[0][0] or 0) if rows else 0
    return out


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(argv or [])
    days, ws = 7.0, None
    while argv:
        a = argv.pop(0)
        if a == "--days" and argv:
            days = float(argv.pop(0))
        elif a == "--workspace" and argv:
            ws = argv.pop(0)
        else:
            print("usage: baton gc [--days N] [--workspace NAME]", file=sys.stderr)
            return 2
    from baton.graph.client import Store
    from baton.service import default_workspace

    ws = ws or os.environ.get("BATON_WORKSPACE") or default_workspace()
    res = collect(Store(ws), days)
    print("graph baton_%s: removed %d finished sessions, %d old handoffs, %d unreferenced files (older than %g days)"
          % (ws, res["sessions"], res["handoffs"], res["artifacts"], days))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
