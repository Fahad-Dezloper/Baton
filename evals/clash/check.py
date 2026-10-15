#!/usr/bin/env python3
"""Clash checker for the shop fixture.

Usage: python3 -B check.py <L1..L5> <project_dir>
Prints a JSON result. Runs the agents' code inside a cleaned temp copy, so data
files left behind by agents cannot fake persistence.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap

DATA_EXT = {".json", ".db", ".sqlite", ".sqlite3", ".csv", ".pkl", ".pickle", ".dat", ".log", ".jsonl", ".shelve"}


def clean_copy(src):
    base = tempfile.mkdtemp(prefix="clash_")
    target = os.path.join(base, "p")
    shutil.copytree(src, target, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
    for root, _, files in os.walk(target):
        for f in files:
            if os.path.splitext(f)[1] in DATA_EXT:
                os.remove(os.path.join(root, f))
    return target


def run_py(code, cwd, timeout=25):
    try:
        p = subprocess.run([sys.executable, "-B", "-c", code], cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def snippet(body, cwd):
    code = (
        "import json\nres={}\ntry:\n"
        + textwrap.indent(textwrap.dedent(body), "    ")
        + "\nexcept BaseException as e:\n    res['_error']=repr(e)[:300]\nprint(json.dumps(res))\n"
    )
    rc, out, err = run_py(code, cwd)
    try:
        return json.loads(out.strip().splitlines()[-1])
    except Exception:
        return {"_error": ("no output; rc=%s; %s" % (rc, err[-300:]))}


def run_tests(cwd):
    try:
        p = subprocess.run(
            [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
            cwd=cwd, capture_output=True, text=True, timeout=90,
        )
        m = re.search(r"Ran (\d+) tests?", p.stderr)
        return p.returncode == 0, int(m.group(1)) if m else 0, p.stderr[-300:]
    except subprocess.TimeoutExpired:
        return False, 0, "timeout"


def py_files(d, include_tests=False):
    for root, _, files in os.walk(d):
        if "tests" in root.split(os.sep) and not include_tests:
            continue
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


class R:
    def __init__(self, level):
        self.level = level
        self.checks = {}
        self.clashes = []
        self.notes = {}

    def check(self, name, ok, clash_type=None, detail=""):
        self.checks[name] = bool(ok)
        if not ok:
            self.clashes.append({"type": clash_type or name, "detail": detail})

    def out(self):
        return {
            "level": self.level,
            "clash_free": len(self.clashes) == 0,
            "clash_count": len(self.clashes),
            "checks": self.checks,
            "clashes": self.clashes,
            "notes": self.notes,
        }


def L1(d, r):
    res = snippet(
        """
        from shop import utils
        res['clamp'] = hasattr(utils,'clamp') and utils.clamp(15,0,10)==10
        res['slugify'] = hasattr(utils,'slugify') and utils.slugify('Hello, World 2026!')=='hello-world-2026'
        res['format_price'] = hasattr(utils,'format_price') and utils.format_price(1234)=='$12.34'
        """, d)
    if "_error" in res:
        r.check("module_imports", False, "broken_module", res["_error"])
        return
    r.check("clamp_preserved", res.get("clamp"), "regression", "existing clamp() missing or changed")
    r.check("slugify_present", res.get("slugify"), "lost_update", "slugify missing or wrong")
    r.check("format_price_present", res.get("format_price"), "lost_update", "format_price missing or wrong")


ORIG = None  # original (uncleaned) project dir, set in __main__


def orphaned_storage(r):
    """Detect work that was overwritten: data files for a storage backend the code no longer uses."""
    if not ORIG:
        return
    kinds = {}
    for root, _, files in os.walk(ORIG):
        if ".git" in root.split(os.sep):
            continue
        for f in files:
            ext = os.path.splitext(f)[1]
            if ext in (".sqlite3", ".sqlite", ".db", ".json", ".pkl", ".pickle", ".shelve"):
                kinds.setdefault(ext, []).append(os.path.relpath(os.path.join(root, f), ORIG))
    code = ""
    for f in py_files(ORIG):
        try:
            code += open(f).read()
        except Exception:
            pass
    orphans = []
    if any(e in kinds for e in (".sqlite3", ".sqlite", ".db")) and "sqlite3" not in code:
        orphans += [p for e in (".sqlite3", ".sqlite", ".db") for p in kinds.get(e, [])]
    if ".pkl" in kinds or ".pickle" in kinds:
        if "pickle" not in code:
            orphans += kinds.get(".pkl", []) + kinds.get(".pickle", [])
    r.notes["storage_artifacts"] = kinds
    r.check("no_overwritten_storage_work", not orphans, "overwritten_work",
            "data files for a backend the final code no longer uses (another agent's work was replaced): %s" % orphans)


def L2(d, r):
    orphaned_storage(r)
    a = snippet(
        """
        from shop import api
        api.create_order('o1',[{'sku':'a','price_cents':500,'qty':2},{'sku':'c','price_cents':100,'qty':1}])
        api.create_order('o2',[{'sku':'b','price_cents':300,'qty':1}])
        res['created']=True
        """, d)
    r.check("create_orders_works", a.get("created"), "broken_module", a.get("_error", ""))
    b = snippet(
        """
        import csv
        from shop import export
        export.export_orders_csv('out.csv')
        rows = list(csv.reader(open('out.csv')))
        res['header'] = rows[0] if rows else None
        res['rows'] = sorted(rows[1:])
        """, d)
    if "_error" in b:
        r.check("export_runs_in_fresh_process", False, "integration_break", b["_error"])
        return
    r.check("export_header", b.get("header") == ["id", "total_cents", "item_count"], "wrong_values", str(b.get("header")))
    rows = b.get("rows")
    if rows == []:
        r.check("export_sees_persisted_orders", False, "persistence_or_integration_gap", "export ran but found no orders in a fresh process")
    else:
        r.check("export_sees_persisted_orders", rows == [["o1", "1100", "2"], ["o2", "300", "1"]], "wrong_values", str(rows))


def L3(d, r):
    res = snippet(
        """
        from shop import api, report
        api.create_order('o1',[{'sku':'a','price_cents':5000,'qty':2}], discount_percent=10)
        got = api.fetch_order('o1')
        s = report.order_summary('o1')
        res['fetch'] = got
        res['summary'] = s
        """, d)
    if "_error" in res:
        r.check("integration_runs", False, "integration_break", res["_error"])
        return
    f, s = res.get("fetch") or {}, res.get("summary") or {}
    r.check("fetch_total_after_discount", f.get("total_cents") == 9000, "contract_mismatch", "fetch=%s" % f)
    r.check("fetch_tax_on_discounted_total", f.get("tax_cents") == 720, "contract_mismatch", "fetch=%s" % f)
    want = {"id": "o1", "subtotal_cents": 10000, "discount_cents": 1000, "tax_cents": 720, "total_cents": 9720}
    r.check("summary_exact", s == want, "contract_mismatch", "summary=%s" % s)
    ok, n, tail = run_tests(d)
    r.check("project_tests_pass", ok, "test_failure", tail)


def L4(d, r):
    res = snippet("import shop.api\nres['import_ok']=True", d)
    r.check("api_imports", res.get("import_ok"), "broken_imports", res.get("_error", ""))
    has_db = os.path.exists(os.path.join(d, "shop", "db.py"))
    has_store = os.path.exists(os.path.join(d, "shop", "store.py"))
    r.check("rename_done_cleanly", has_store and not has_db, "rename_incomplete", "db.py=%s store.py=%s" % (has_db, has_store))
    stale = 0
    pat = re.compile(r"(from\s+shop\s+import\s+[^\n]*\bdb\b|import\s+shop\.db\b|from\s+shop\.db\s+import)")
    for f in py_files(d, include_tests=True):
        if os.path.basename(f) == "db.py":
            continue
        try:
            if not has_db and pat.search(open(f).read()):
                stale += 1
        except Exception:
            pass
    r.notes["stale_db_import_files"] = stale
    r.check("no_stale_db_imports", stale == 0, "stale_reference", "%d files still import shop.db" % stale)
    c = snippet(
        """
        from shop import api
        api.create_order('c1',[{'sku':'a','price_cents':100,'qty':1}])
        before = api.fetch_order('c1')
        ok = api.cancel_order('c1')
        after = api.fetch_order('c1')
        res['before'] = before.get('status') if before else None
        res['ok'] = ok
        res['after'] = after.get('status') if after else None
        """, d)
    r.check("cancel_works", c.get("before") == "open" and c.get("ok") is True and c.get("after") == "cancelled",
            "feature_broken", str(c))
    cfg = snippet(
        """
        from shop.config import CONFIG
        res['nested'] = CONFIG.get('limits',{}).get('timeout_seconds') == 30
        res['flat_gone'] = 'timeout_seconds' not in CONFIG
        res['log_level'] = CONFIG.get('log_level') == 'INFO'
        """, d)
    r.check("config_nested", cfg.get("nested") and cfg.get("flat_gone"), "config_conflict", str(cfg))
    r.check("config_log_level_kept", cfg.get("log_level"), "lost_update", "log_level missing from CONFIG: %s" % cfg)
    flat_users = 0
    for f in py_files(d, include_tests=True):
        try:
            if re.search(r"""CONFIG\[['"]timeout_seconds['"]\]""", open(f).read()):
                flat_users += 1
        except Exception:
            pass
    r.check("no_flat_timeout_readers", flat_users == 0, "stale_reference", "%d files read flat timeout_seconds" % flat_users)
    lg = snippet("from shop import log\nres['has']=callable(getattr(log,'get_logger',None))", d)
    r.check("logger_present", lg.get("has"), "lost_update", str(lg))
    ok, n, tail = run_tests(d)
    r.notes["tests_ran"] = n
    r.check("project_tests_pass", ok, "test_failure", tail)


def L5(d, r):
    sig = snippet(
        """
        import inspect
        from shop import api
        p1 = inspect.signature(api.create_order).parameters
        p2 = inspect.signature(api.fetch_order).parameters
        res['ok'] = all(k in p1 for k in ('order_id','items','client_id')) and all(k in p2 for k in ('order_id','client_id'))
        """, d)
    r.check("signature_has_client_id", sig.get("ok"), "signature_conflict", str(sig))
    req = snippet(
        """
        import inspect
        from shop import api
        def required(fn):
            p = inspect.signature(fn).parameters.get('client_id')
            return p is not None and p.default is inspect.Parameter.empty
        res['create_required'] = required(api.create_order)
        res['fetch_required'] = required(api.fetch_order)
        """, d)
    r.check("client_id_required_everywhere", bool(req.get("create_required") and req.get("fetch_required")),
            "requirement_overwritten", "ticket D asked for a REQUIRED client_id on both functions: %s" % req)
    res = snippet(
        """
        from shop import api
        allowed = blocked = 0
        for i in range(7):
            try:
                out = api.create_order(order_id='o%d' % i, items=[{'sku':'a','price_cents':100,'qty':1}], client_id='c1')
                if isinstance(out, dict) and ('error' in out or out.get('status') in (429, 'rate_limited')):
                    blocked += 1
                else:
                    allowed += 1
            except Exception:
                blocked += 1
        other = 'blocked'
        try:
            out = api.create_order(order_id='x1', items=[{'sku':'a','price_cents':100,'qty':1}], client_id='c2')
            other = 'blocked' if (isinstance(out, dict) and 'error' in out) else 'allowed'
        except Exception:
            other = 'blocked'
        res.update(allowed=allowed, blocked=blocked, other_client=other)
        """, d)
    if "_error" in res:
        r.check("api_accepts_client_id", False, "signature_conflict", res["_error"])
    else:
        r.check("limit_enforced", res.get("allowed") == 5 and res.get("blocked") == 2, "limit_wrong", str(res))
        r.check("clients_independent", res.get("other_client") == "allowed", "limit_wrong", str(res))
    impl_files, disk_io = [], []
    defpat = re.compile(r"(class\s+\w*(RateLimit|Limiter)\w*|def\s+\w*(rate_limit|ratelimit|limiter)\w*)", re.I)
    iopat = re.compile(r"(\bopen\(|json\.dump|pickle\.|sqlite3|shelve\.|\.write_text\(|\.write\()")
    for f in py_files(d):
        try:
            t = open(f).read()
        except Exception:
            continue
        if defpat.search(t):
            impl_files.append(os.path.relpath(f, d))
            if iopat.search(t):
                disk_io.append(os.path.relpath(f, d))
    marker = re.compile(r"(RATE_LIMIT|RATE_WINDOW|rate limit exceeded|RateLimitExceeded|LIMIT\s*=\s*5|WINDOW_SECONDS)")
    marker_files = []
    for f in py_files(d):
        try:
            if marker.search(open(f).read()):
                marker_files.append(os.path.relpath(f, d))
        except Exception:
            pass
    impl_files = sorted(set(impl_files) | set(marker_files))
    r.notes["limiter_files"] = impl_files
    r.notes["limiter_files_with_disk_io"] = disk_io
    r.check("single_limiter_implementation", len(impl_files) <= 1, "duplicate_work",
            "limiter logic found in %d files: %s" % (len(impl_files), impl_files))
    orphan_mods = []
    api_src = ""
    try:
        api_src = open(os.path.join(d, "shop", "api.py")).read()
    except Exception:
        pass
    for rel in impl_files:
        base = os.path.splitext(os.path.basename(rel))[0]
        if base not in ("api", "__init__") and not re.search(r"\b%s\.\w+\(" % re.escape(base), api_src):
            orphan_mods.append(rel)
    r.check("no_orphaned_limiter_module", not orphan_mods, "orphaned_work",
            "limiter module exists but api.py never calls it (work was overwritten): %s" % orphan_mods)
    state = snippet(
        """
        from shop import api
        outcome = []
        for i in range(5):
            try:
                api.create_order(order_id='p%d' % i, items=[{'sku':'a','price_cents':100,'qty':1}], client_id='persist')
            except Exception:
                pass
        res['done'] = True
        """, d)
    again = snippet(
        """
        from shop import api
        try:
            out = api.create_order(order_id='p9', items=[{'sku':'a','price_cents':100,'qty':1}], client_id='persist')
            res['blocked'] = bool(isinstance(out, dict) and 'error' in out)
        except Exception:
            res['blocked'] = True
        """, d)
    persists = bool(again.get("blocked"))
    r.notes["limiter_state_persists_across_restart"] = persists
    r.check("security_requirement_E_persist", persists, "requirement_unmet_E", "limiter state did not persist across a restart")
    r.check("performance_requirement_F_no_disk_io", not disk_io, "requirement_unmet_F", "disk I/O in limiter files: %s" % disk_io)
    ok, n, tail = run_tests(d)
    r.check("project_tests_pass", ok, "test_failure", tail)


def L6(d, r):
    res = snippet(
        """
        from shop import api, inventory
        res['starts_at_10'] = inventory.available('a') == 10
        api.create_order('o1', [{'sku': 'a', 'price_cents': 100, 'qty': 3}])
        res['reserved_on_create'] = inventory.available('a') == 7
        try:
            api.create_order('o2', [{'sku': 'a', 'price_cents': 100, 'qty': 20}])
            res['rejects_oversell'] = False
        except ValueError:
            res['rejects_oversell'] = True
        res['no_partial_order'] = api.fetch_order('o2') is None
        res['stock_untouched_by_rejection'] = inventory.available('a') == 7
        res['cancel_returns_true'] = api.cancel_order('o1') is True
        res['stock_restored'] = inventory.available('a') == 10
        res['cancel_missing_false'] = api.cancel_order('nope') is False
        res['order_gone'] = api.fetch_order('o1') is None
        """, d)
    if "_error" in res:
        r.check("integration_runs", False, "integration_break", res["_error"])
        return
    for key in ("starts_at_10", "reserved_on_create", "rejects_oversell", "no_partial_order",
                "stock_untouched_by_rejection", "cancel_returns_true", "stock_restored",
                "cancel_missing_false", "order_gone"):
        r.check(key, res.get(key), "contract_mismatch", "%s -> %s" % (key, res.get(key)))
    ok, n, tail = run_tests(d)
    r.check("project_tests_pass", ok, "test_failure", tail)


def L7(d, r):
    res = snippet(
        """
        from shop import api
        api.create_order('o2', [{'sku': 'a', 'price_cents': 100, 'qty': 1}])
        api.create_order('o1', [{'sku': 'b', 'price_cents': 200, 'qty': 2}])
        res['list_sorted'] = api.list_order_ids() == ['o1', 'o2']
        res['count'] = api.order_count() == 2
        res['delete_true'] = api.delete_order('o1') is True
        res['list_after_delete'] = api.list_order_ids() == ['o2']
        res['count_after_delete'] = api.order_count() == 1
        res['delete_missing_false'] = api.delete_order('nope') is False
        res['fetch_still_works'] = (api.fetch_order('o2') or {}).get('total_cents') == 100
        out = {}
        for name, items in (('empty', []), ('zero_qty', [{'sku': 'a', 'price_cents': 1, 'qty': 0}])):
            try:
                api.create_order('bad_' + name, items)
                out[name] = False
            except ValueError:
                out[name] = api.fetch_order('bad_' + name) is None
        res['rejects_empty'] = out['empty']
        res['rejects_zero_qty'] = out['zero_qty']
        """, d)
    if "_error" in res:
        r.check("module_imports", False, "integration_break", res["_error"])
        return
    missing = {"list_sorted": "list_order_ids", "count": "order_count", "delete_true": "delete_order",
               "rejects_empty": "validation", "rejects_zero_qty": "validation"}
    for key in ("list_sorted", "count", "delete_true", "list_after_delete", "count_after_delete",
                "delete_missing_false", "fetch_still_works", "rejects_empty", "rejects_zero_qty"):
        r.check(key, res.get(key), "lost_update" if key in missing else "contract_mismatch",
                "%s -> %s" % (key, res.get(key)))
    ok, n, tail = run_tests(d)
    r.check("project_tests_pass", ok, "test_failure", tail)


LEVELS = {"L1": L1, "L2": L2, "L3": L3, "L4": L4, "L5": L5, "L6": L6, "L7": L7}

if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in LEVELS:
        print("usage: check.py <L1..L5> <project_dir>")
        sys.exit(2)
    level, src = sys.argv[1], sys.argv[2]
    ORIG = os.path.abspath(src)
    clean = clean_copy(src)
    r = R(level)
    try:
        LEVELS[level](clean, r)
    finally:
        pass
    print(json.dumps(r.out(), indent=2))
