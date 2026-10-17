"""The held-out level checkers must accept a correct solution and reject wrong ones."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIXTURE = os.path.join(ROOT, "evals", "clash", "fixture")
CHECK = os.path.join(ROOT, "evals", "clash", "check.py")

DB = '''_ORDERS = {}


def save_order(order):
    _ORDERS[order.id] = order


def get_order(order_id):
    return _ORDERS.get(order_id)


def delete_order(order_id):
    return _ORDERS.pop(order_id, None) is not None


def all_ids():
    return sorted(_ORDERS)
'''

INVENTORY = '''_STOCK = {}
DEFAULT = 10


def available(sku):
    return _STOCK.get(sku, DEFAULT)


def reserve(sku, qty):
    if qty > available(sku):
        raise ValueError("insufficient stock")
    _STOCK[sku] = available(sku) - qty


def release(sku, qty):
    _STOCK[sku] = available(sku) + qty
'''

API_L6 = '''from shop.models import Order, Item
from shop import db, inventory


def create_order(order_id, items):
    for i in items:
        if i.get("qty", 1) > inventory.available(i["sku"]):
            raise ValueError("insufficient stock")
    order = Order(id=order_id, items=[Item(**i) for i in items])
    db.save_order(order)
    for it in order.items:
        inventory.reserve(it.sku, it.qty)
    return {"id": order.id, "total_cents": order.total_cents}


def fetch_order(order_id):
    order = db.get_order(order_id)
    if order is None:
        return None
    return {"id": order.id, "total_cents": order.total_cents}


def cancel_order(order_id):
    order = db.get_order(order_id)
    if order is None:
        return False
    for it in order.items:
        inventory.release(it.sku, it.qty)
    return db.delete_order(order_id)
'''

API_L7 = '''from shop.models import Order, Item
from shop import db


def create_order(order_id, items):
    if not items or any(i.get("qty", 1) <= 0 for i in items):
        raise ValueError("invalid items")
    order = Order(id=order_id, items=[Item(**i) for i in items])
    db.save_order(order)
    return {"id": order.id, "total_cents": order.total_cents}


def fetch_order(order_id):
    order = db.get_order(order_id)
    if order is None:
        return None
    return {"id": order.id, "total_cents": order.total_cents}


def list_order_ids():
    return db.all_ids()


def delete_order(order_id):
    return db.delete_order(order_id)


def order_count():
    return len(db.all_ids())
'''


def make_project(files=None):
    d = tempfile.mkdtemp(prefix="baton_chk_")
    target = os.path.join(d, "p")
    shutil.copytree(FIXTURE, target)
    for rel, text in (files or {}).items():
        with open(os.path.join(target, rel), "w") as f:
            f.write(text)
    return target


def run_check(level, project):
    p = subprocess.run([sys.executable, "-B", CHECK, level, project], capture_output=True, text=True, timeout=120)
    return json.loads(p.stdout)


# ---- held-out round 2 (L8-L10): reference solutions -------------------------------------------
DB_L8 = DB.replace("def get_order", "def load_order")
API_L8 = '''from shop.models import Order, Item
from shop import db


def create_order(order_id, items):
    order = Order(id=order_id, items=[Item(**i) for i in items])
    db.save_order(order)
    return {"id": order.id, "total_cents": order.total_cents}


def fetch_order(order_id):
    order = db.load_order(order_id)
    if order is None:
        return None
    return {"id": order.id, "total_cents": order.total_cents}


def order_exists(order_id):
    return db.load_order(order_id) is not None
'''
AUDIT_L8 = '''from shop import db


def order_total(order_id):
    order = db.load_order(order_id)
    return None if order is None else order.total_cents
'''

CONFIG_L9 = '''CONFIG = {
    "currency": "USD",
    "timeout_ms": 30000,
}
'''
CLIENT_L9 = '''from shop.config import CONFIG


def get_timeout():
    return CONFIG["timeout_ms"] / 1000.0
'''
RETRY_L9 = '''from shop.config import CONFIG


def retry_budget_seconds():
    return 3 * CONFIG["timeout_ms"] / 1000.0
'''

VALIDATORS_L10 = '''import re

VALIDATORS = {}


def validate(kind, value):
    return VALIDATORS[kind](value)


VALIDATORS["sku"] = lambda v: isinstance(v, str) and re.fullmatch(r"[a-z0-9]+", v) is not None
VALIDATORS["qty"] = lambda v: isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 999
VALIDATORS["email"] = lambda v: isinstance(v, str) and v.count("@") == 1 and "." in v.split("@")[1]
'''


class HeldOutCheckerTests(unittest.TestCase):
    def test_l6_accepts_reference_solution(self):
        res = run_check("L6", make_project({"shop/db.py": DB, "shop/inventory.py": INVENTORY,
                                            "shop/api.py": API_L6}))
        self.assertTrue(res["clash_free"], res["clashes"])

    def test_l6_rejects_pristine_and_broken_variants(self):
        self.assertFalse(run_check("L6", make_project())["clash_free"])
        # cancel does not return stock
        broken = API_L6.replace("        inventory.release(it.sku, it.qty)\n", "        pass\n")
        res = run_check("L6", make_project({"shop/db.py": DB, "shop/inventory.py": INVENTORY,
                                            "shop/api.py": broken}))
        self.assertFalse(res["checks"]["stock_restored"])
        # create does not reserve
        broken = API_L6.replace("    for it in order.items:\n        inventory.reserve(it.sku, it.qty)\n", "")
        res = run_check("L6", make_project({"shop/db.py": DB, "shop/inventory.py": INVENTORY,
                                            "shop/api.py": broken}))
        self.assertFalse(res["checks"]["reserved_on_create"])

    def test_l7_accepts_reference_solution(self):
        res = run_check("L7", make_project({"shop/db.py": DB, "shop/api.py": API_L7}))
        self.assertTrue(res["clash_free"], res["clashes"])

    def test_l7_flags_each_lost_addition(self):
        self.assertFalse(run_check("L7", make_project())["clash_free"])
        for fn in ("list_order_ids", "order_count", "delete_order"):
            lines = API_L7.split("\n\n\n")
            kept = [b for b in lines if not b.startswith("def %s" % fn)]
            res = run_check("L7", make_project({"shop/db.py": DB, "shop/api.py": "\n\n\n".join(kept)}))
            self.assertFalse(res["clash_free"], fn)
        # validation lost
        no_validation = API_L7.replace(
            '    if not items or any(i.get("qty", 1) <= 0 for i in items):\n        raise ValueError("invalid items")\n', "")
        res = run_check("L7", make_project({"shop/db.py": DB, "shop/api.py": no_validation}))
        self.assertFalse(res["checks"]["rejects_empty"])


class HeldOutRound2Tests(unittest.TestCase):
    """L8-L10 were written and validated here before any trial ran."""

    def l8(self, **over):
        files = {"shop/db.py": DB_L8, "shop/api.py": API_L8, "shop/audit.py": AUDIT_L8}
        files.update(over)
        return run_check("L8", make_project(files))

    def l9(self, **over):
        files = {"shop/config.py": CONFIG_L9, "shop/client.py": CLIENT_L9, "shop/retry.py": RETRY_L9}
        files.update(over)
        return run_check("L9", make_project(files))

    def l10(self, **over):
        files = {"shop/validators.py": VALIDATORS_L10}
        files.update(over)
        return run_check("L10", make_project(files))

    # L8
    def test_l8_accepts_reference_solution(self):
        res = self.l8()
        self.assertTrue(res["clash_free"], res["clashes"])

    def test_l8_rejects_pristine(self):
        res = run_check("L8", make_project())
        self.assertFalse(res["clash_free"])
        self.assertFalse(res["checks"]["load_order_exists"])

    def test_l8_flags_new_callers_written_against_old_name(self):
        res = self.l8(**{"shop/audit.py": AUDIT_L8.replace("load_order", "get_order")})
        self.assertFalse(res["checks"]["audit_order_total_works"])
        self.assertFalse(res["checks"]["no_stale_get_order_refs"])
        res = self.l8(**{"shop/api.py": API_L8.replace("db.load_order(order_id) is not None", "db.get_order(order_id) is not None")})
        self.assertFalse(res["checks"]["order_exists_works"])

    def test_l8_flags_rename_not_applied_to_existing_callers(self):
        res = self.l8(**{"shop/api.py": API_L8.replace("order = db.load_order", "order = db.get_order")})
        self.assertFalse(res["checks"]["existing_api_still_works"])

    def test_l8_flags_alias_left_behind_and_missing_feature(self):
        res = self.l8(**{"shop/db.py": DB_L8 + "\n\nget_order = load_order\n"})
        self.assertFalse(res["checks"]["get_order_removed"])
        pristine_db_plus_new = self.l8(**{"shop/db.py": DB})
        self.assertFalse(pristine_db_plus_new["checks"]["load_order_exists"])

    # L9
    def test_l9_accepts_reference_solution(self):
        res = self.l9()
        self.assertTrue(res["clash_free"], res["clashes"])

    def test_l9_accepts_features_read_before_rename_if_config_untouched(self):
        # Rename never happened but features read the old key: a different failure, not accepted.
        res = run_check("L9", make_project({
            "shop/client.py": CLIENT_L9.replace("timeout_ms", "timeout_seconds").replace(" / 1000.0", " * 1.0"),
            "shop/retry.py": RETRY_L9.replace("timeout_ms", "timeout_seconds").replace(" / 1000.0", " * 1.0")}))
        self.assertFalse(res["checks"]["config_has_timeout_ms"])
        self.assertTrue(res["checks"]["client_timeout_seconds"])
        self.assertTrue(res["checks"]["retry_budget_seconds"])

    def test_l9_rejects_pristine_and_stale_readers(self):
        self.assertFalse(run_check("L9", make_project())["clash_free"])
        stale = CLIENT_L9.replace("timeout_ms", "timeout_seconds").replace(" / 1000.0", " * 1.0")
        res = self.l9(**{"shop/client.py": stale})
        self.assertFalse(res["checks"]["client_timeout_seconds"])
        self.assertTrue(res["checks"]["retry_budget_seconds"])

    def test_l9_flags_unit_mismatch_and_cached_config(self):
        res = self.l9(**{"shop/client.py": CLIENT_L9.replace(" / 1000.0", "")})
        self.assertFalse(res["checks"]["client_timeout_seconds"])
        cached = CLIENT_L9.replace("def get_timeout():\n    return CONFIG[\"timeout_ms\"] / 1000.0",
                                   "_T = CONFIG[\"timeout_ms\"] / 1000.0\n\n\ndef get_timeout():\n    return _T")
        res = self.l9(**{"shop/client.py": cached})
        self.assertFalse(res["checks"]["client_timeout_seconds"])
        res = self.l9(**{"shop/config.py": CONFIG_L9.replace('    "timeout_ms": 30000,\n', '    "timeout_ms": 30000,\n    "timeout_seconds": 30,\n')})
        self.assertFalse(res["checks"]["config_old_key_removed"])

    # L10
    def test_l10_accepts_reference_solution(self):
        res = self.l10()
        self.assertTrue(res["clash_free"], res["clashes"])

    def test_l10_rejects_pristine(self):
        res = run_check("L10", make_project())
        self.assertFalse(res["clash_free"])

    def test_l10_flags_each_lost_registration(self):
        for kind in ("sku", "qty", "email"):
            kept = [ln for ln in VALIDATORS_L10.split("\n") if not ln.startswith('VALIDATORS["%s"]' % kind)]
            res = self.l10(**{"shop/validators.py": "\n".join(kept)})
            self.assertFalse(res["checks"]["validator_%s_registered" % kind], kind)
            self.assertFalse(res["clash_free"], kind)

    def test_l10_flags_wrong_validators_and_missing_dispatch(self):
        res = self.l10(**{"shop/validators.py": VALIDATORS_L10.replace("1 <= v <= 999", "1 <= v <= 99")})
        self.assertFalse(res["checks"]["validator_qty_correct"])
        res = self.l10(**{"shop/validators.py": VALIDATORS_L10.replace('v.count("@") == 1', 'v.count("@") >= 1')})
        self.assertFalse(res["checks"]["validator_email_correct"])
        res = self.l10(**{"shop/validators.py": VALIDATORS_L10.replace("    return VALIDATORS[kind](value)", "    return VALIDATORS.get(kind, lambda v: False)(value)")})
        self.assertFalse(res["checks"]["unknown_kind_raises_keyerror"])
        res = self.l10(**{"shop/validators.py": VALIDATORS_L10.replace("def validate(kind, value):\n    return VALIDATORS[kind](value)\n", "")})
        self.assertFalse(res["checks"]["registry_and_validate_present"])

    def test_l10_flags_second_registry_file(self):
        res = self.l10(**{"shop/extra.py": "VALIDATORS = {}\n"})
        self.assertFalse(res["checks"]["single_registry"])


if __name__ == "__main__":
    unittest.main()
