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


if __name__ == "__main__":
    unittest.main()
