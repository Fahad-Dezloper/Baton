import time
import unittest

from tests.support import GraphCase

from baton.graph.client import Store
from baton.service import Service, default_workspace


class ServiceTests(GraphCase):
    def svc(self, actor):
        return Service(self.store, base_actor=actor)

    def test_two_sessions_claim_conflict_and_handoff(self):
        a, b = self.svc("sess-a"), self.svc("sess-b")
        t = a.create_task("rename db module", touches=["shop/db.py"])["task"]
        self.assertTrue(a.claim_task(t["id"])["claimed"])
        r = b.claim_task(t["id"])
        self.assertFalse(r["claimed"])
        self.assertEqual((r["reason"], r["holder"]), ("held", "sess-a"))
        a.post_decision("db.py becomes store.py", ["shop/db.py"], kind="rename")
        c = b.check_conflicts(["./shop/db.py"])
        self.assertTrue(c["has_conflicts"])
        self.assertIn("rename decision by sess-a", c["summary"])
        self.assertFalse(a.check_conflicts(["shop/db.py"])["has_conflicts"])
        self.assertTrue(a.complete_task(t["id"])["completed"])
        ex = a.handoff_export(t["id"])
        self.assertTrue(ex["ok"])
        imp = b.handoff_import(ex["handoff_id"])
        self.assertEqual(imp["task_id"], t["id"])
        self.assertIn("db.py becomes store.py", imp["text"])

    def test_actor_label_is_qualifier_only(self):
        s = self.svc("sess-x")
        self.assertEqual(s.actor(), "sess-x")
        self.assertEqual(s.actor("sub agent!"), "sess-x/subagent")
        self.assertEqual(s.actor("!!!"), "sess-x")

    def test_retract_reports_blast_radius(self):
        s = self.svc("sess-r")
        f = s.add_finding("timeout is 5s", "notes.md")["finding"]
        d1 = s.post_decision("client timeout 5s", based_on=[f["id"]])["decision"]
        d2 = s.post_decision("docs mention 5s", based_on=[d1["id"]])["decision"]
        r = s.retract(f["id"], "spec says 30s")
        self.assertTrue(r["ok"])
        self.assertEqual(r["tainted_count"], 2)
        self.assertEqual({x["id"] for x in r["tainted"]}, {d1["id"], d2["id"]})
        self.assertEqual(s.why(d2["id"])["findings"][0]["id"], f["id"])

    def test_caller_mistakes_are_structured_not_raised(self):
        s = self.svc("sess-e")
        self.assertEqual(s.complete_task("nope")["completed"], False)
        self.assertEqual(s.why("nope")["error"], "not_found")
        self.assertEqual(s.retract("nope")["error"], "not_found")
        self.assertEqual(s.create_task("  ")["error"], "invalid")
        self.assertEqual(s.post_decision("x", kind="bogus")["error"], "invalid")
        self.assertEqual(s.handoff_import("nope")["error"], "not_found")

    def test_inputs_are_bounded(self):
        s = self.svc("sess-b2")
        d = s.post_decision("x" * 10_000, artifacts=["p%d.py" % i for i in range(500)])["decision"]
        self.assertLessEqual(len(d["text"]), 2000)
        n = len(s.check_conflicts(["p%d.py" % i for i in range(500)])["paths"])
        self.assertLessEqual(n, 50)

    def test_degraded_when_store_unreachable(self):
        dead = Service(Store("dead_ws", port=6399), base_actor="sess-d")
        t0 = time.time()
        r = dead.check_conflicts(["a.py"])
        self.assertFalse(r["ok"])
        self.assertTrue(r["degraded"])
        self.assertEqual(r["error"], "baton_unavailable")
        self.assertLess(time.time() - t0, 8)

    def test_default_workspace_is_stable_and_cwd_derived(self):
        self.assertEqual(default_workspace("/tmp/proj"), default_workspace("/tmp/proj"))
        self.assertNotEqual(default_workspace("/tmp/proj"), default_workspace("/tmp/other"))
        self.assertTrue(default_workspace("/tmp/proj").startswith("proj-"))


if __name__ == "__main__":
    unittest.main()
