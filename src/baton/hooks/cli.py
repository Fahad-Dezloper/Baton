"""Hook entry point called by the host:  baton <event>   (JSON on stdin, JSON on stdout).

Policy: fail open. Any error, missing store or disabled config produces no output and exit 0, so
baton can never block or break the host session.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import List, Optional

SUBCOMMANDS = ("session-start", "prompt", "pre-tool", "post-tool", "stop", "session-end")


def _debug(record: dict) -> None:
    path = os.environ.get("BATON_DEBUG_LOG")
    if not path:
        return
    try:
        with open(path, "a") as f:
            f.write(json.dumps({"ts": time.time(), **record}) + "\n")
    except OSError:
        pass


def main(argv: Optional[List[str]] = None, stdin=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in SUBCOMMANDS:
        print("usage: baton {%s}" % "|".join(SUBCOMMANDS), file=sys.stderr)
        return 2
    event = argv[0]
    stream = stdin if stdin is not None else sys.stdin
    try:
        raw = "" if getattr(stream, "isatty", lambda: False)() else stream.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    t0 = time.time()
    try:
        # Imported lazily so a broken environment still exits 0 above.
        from baton.graph.client import Store
        from baton.hooks.config import load_config
        from baton.hooks.events import HANDLERS, project_dir_from
        from baton.service import default_workspace

        os.environ.setdefault("BATON_CONNECT_TIMEOUT", "1")
        os.environ.setdefault("BATON_QUERY_TIMEOUT", "3")
        project = project_dir_from(payload)
        cfg = load_config(project)
        if not cfg.enabled:
            return 0
        if event in ("pre-tool", "post-tool"):
            from baton.hooks.events import edit_paths

            if not edit_paths(payload, project):
                return 0  # not an edit or rename: skip the database entirely
        workspace = os.environ.get("BATON_WORKSPACE") or default_workspace(project)
        out = HANDLERS[event](Store(workspace), payload, cfg)
        if out:
            sys.stdout.write(json.dumps(out))
            sys.stdout.flush()
        _debug({"event": event, "ms": round((time.time() - t0) * 1000), "output": out})
    except Exception as e:  # fail open
        _debug({"event": event, "error": "%s: %s" % (type(e).__name__, str(e)[:200])})
    return 0


if __name__ == "__main__":
    sys.exit(main())
