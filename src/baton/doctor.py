"""`baton doctor`: check that a fresh install can actually run, with a fix for each failure.

Read-only apart from one throwaway graph (named baton_doctor_<random>) that is deleted afterwards.
"""

from __future__ import annotations

import importlib
import os
import sys
import uuid
from typing import Callable, List, Optional, Tuple

MIN_PYTHON = (3, 10)
PLUGIN_FILES = (
    ".claude-plugin/plugin.json",
    "hooks/hooks.json",
    "optional-mcp.json",
    "bin/baton-hook",
    "bin/baton-mcp",
)

# (ok, message, fix)
Result = Tuple[bool, str, str]


def check_python(version=None) -> Result:
    v = tuple(version or sys.version_info[:3])
    ok = v[:2] >= MIN_PYTHON
    return (ok, "Python %s" % ".".join(str(x) for x in v[:3]),
            "" if ok else "baton needs Python %d.%d+. Install a newer python3 and recreate the venv." % MIN_PYTHON)


def check_package(name: str, pip_name: Optional[str] = None) -> Result:
    try:
        importlib.import_module(name)
        return (True, "package '%s' importable" % name, "")
    except Exception as e:
        return (False, "package '%s' not importable (%s)" % (name, type(e).__name__),
                "pip install -e .   (inside the repo, using the venv you will run baton with)"
                if name == "baton" else "pip install %s" % (pip_name or name))


def check_plugin_files(plugin_dir: str) -> Result:
    missing = [f for f in PLUGIN_FILES if not os.path.isfile(os.path.join(plugin_dir, f))]
    for f in ("bin/baton-hook", "bin/baton-mcp"):
        p = os.path.join(plugin_dir, f)
        if os.path.isfile(p) and not os.access(p, os.X_OK):
            missing.append(f + " (not executable)")
    if missing:
        return (False, "plugin files missing in %s: %s" % (plugin_dir, ", ".join(missing)),
                "Run from a full clone, or: chmod +x plugin/bin/*")
    return (True, "plugin files present (%s)" % plugin_dir, "")


def find_plugin_dir() -> Optional[str]:
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, "..", "..", "plugin"), os.path.join(os.getcwd(), "plugin")):
        cand = os.path.abspath(cand)
        if os.path.isdir(cand):
            return cand
    return None


def check_falkordb(host: str, port: int) -> Result:
    import socket

    try:
        with socket.create_connection((host, port), timeout=2):
            pass
    except OSError as e:
        return (False, "FalkorDB not reachable at %s:%d (%s)" % (host, port, e.__class__.__name__),
                "docker compose up -d   (or set BATON_FALKORDB_HOST / BATON_FALKORDB_PORT for a remote server)")
    return (True, "FalkorDB reachable at %s:%d" % (host, port), "")


def check_roundtrip() -> Result:
    from baton.graph.client import Store

    store = Store("doctor_" + uuid.uuid4().hex[:8])
    try:
        store.query("CREATE (:Probe {v: $v})", {"v": 42})
        rows = store.rows("MATCH (p:Probe) RETURN p.v", read_only=True)
        if rows != [[42]]:
            return (False, "write/read round trip returned %r" % (rows,),
                    "Check the server is FalkorDB (not plain Redis): docker compose up -d")
        return (True, "write/read round trip in a throwaway graph", "")
    except Exception as e:
        return (False, "round trip failed: %s: %s" % (type(e).__name__, str(e)[:120]),
                "Check the server is FalkorDB (not plain Redis): docker compose up -d")
    finally:
        store.drop()


def run_checks(plugin_dir: Optional[str] = None) -> List[Result]:
    from baton.graph.client import connection_settings

    s = connection_settings()
    results = [check_python(), check_package("baton"), check_package("falkordb"),
               check_package("mcp", "'mcp>=2,<3'")]
    net = check_falkordb(s["host"], s["port"])
    results.append(net)
    if net[0] and results[2][0]:
        results.append(check_roundtrip())
    pdir = plugin_dir or find_plugin_dir()
    results.append(check_plugin_files(pdir) if pdir else
                   (False, "plugin directory not found", "Run `baton doctor` from the repo root"))
    return results


def format_results(results: List[Result]) -> Tuple[str, bool]:
    lines = []
    for ok, msg, fix in results:
        lines.append("%s  %s" % ("PASS" if ok else "FAIL", msg))
        if not ok and fix:
            lines.append("      fix: %s" % fix)
    good = all(r[0] for r in results)
    lines.append("")
    lines.append("All checks passed. Start Claude Code with: claude --plugin-dir %s" % "<repo>/plugin"
                 if good else "Some checks failed; fix the items above and run `baton doctor` again.")
    return "\n".join(lines), good


def main(argv: Optional[List[str]] = None, out: Callable[[str], None] = print) -> int:
    argv = sys.argv[1:] if argv is None else argv
    plugin_dir = argv[0] if argv else None
    text, good = format_results(run_checks(plugin_dir))
    out(text)
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
