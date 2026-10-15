import unittest

from tests.support import GraphCase

from baton.core import decisions, handoff, provenance, tasks


class ProvenanceTests(GraphCase):
    def setUp(self):
        # diamond:   F1 -> D1, D2 -> D3 ;  unrelated: F2 -> D4
        s = self.store
        provenance.add_finding(s, "A", "timeout is 5s", "notes.md", finding_id="F1")
        provenance.add_finding(s, "A", "unrelated fact", "other.md", finding_id="F2")
        decisions.post_decision(s, "A", "set client timeout 5s", based_on=["F1"], decision_id="D1")
        decisions.post_decision(s, "B", "set server timeout 5s", based_on=["F1"], decision_id="D2")
        decisions.post_decision(s, "C", "document both timeouts", based_on=["D1", "D2"], decision_id="D3")
        decisions.post_decision(s, "A", "unrelated decision", based_on=["F2"], decision_id="D4")

    def tearDown(self):
        self.store.query("MATCH (n) DETACH DELETE n")

    def test_why_returns_transitive_sources(self):
        w = provenance.why(self.store, "D3")
        self.assertEqual({d["id"] for d in w["decisions"]}, {"D1", "D2"})
        self.assertEqual({f["id"] for f in w["findings"]}, {"F1"})
        self.assertEqual(provenance.why(self.store, "D4")["findings"][0]["id"], "F2")

    def test_retract_finding_taints_exact_blast_radius(self):
        res = provenance.retract(self.store, "F1", "A", reason="spec says 30s")
        self.assertEqual({d["id"] for d in res["affected"]}, {"D1", "D2", "D3"})
        self.assertEqual(res["root"]["status"], "retracted")
        st = {i: decisions.get_decision(self.store, i)["status"] for i in ("D1", "D2", "D3", "D4")}
        self.assertEqual(st, {"D1": "tainted", "D2": "tainted", "D3": "tainted", "D4": "open"})
        self.assertEqual(decisions.get_decision(self.store, "D3")["tainted_by"], "F1")

    def test_retract_decision_only_hits_its_descendants(self):
        res = provenance.retract(self.store, "D1", "A")
        self.assertEqual({d["id"] for d in res["affected"]}, {"D3"})
        self.assertEqual(decisions.get_decision(self.store, "D2")["status"], "open")
        self.assertEqual(decisions.get_decision(self.store, "D3")["status"], "tainted")

    def test_retract_unknown_item_raises(self):
        with self.assertRaises(KeyError):
            provenance.retract(self.store, "nope", "A")


class HandoffTests(GraphCase):
    def test_export_is_bounded_relevant_and_importable(self):
        s = self.store
        tasks.create_task(s, "migrate storage", touches=["shop/db.py", "shop/config.py"], task_id="mig")
        provenance.add_finding(s, "A", "orders must survive restart", "ticket-12", finding_id="HF1")
        decisions.post_decision(s, "A", "use sqlite", artifacts=["shop/db.py"], based_on=["HF1"],
                                kind="storage", decision_id="HD1")
        decisions.post_decision(s, "A", "unrelated change", artifacts=["shop/utils.py"], decision_id="HD2")
        for i in range(40):
            decisions.post_decision(s, "A", "noise %d " % i + "x" * 600, artifacts=["shop/config.py"])
        pk = handoff.export_handoff(s, "mig", "A", max_items=10, max_chars=3000)
        ids = {d["id"] for d in pk["decisions"]}
        self.assertNotIn("HD2", ids)                    # unrelated artifact excluded
        self.assertEqual(len(pk["decisions"]), 10)       # bounded
        self.assertIn("HD1", ids)                        # important one survives 40 newer notes
        self.assertGreater(pk["omitted"], 0)
        self.assertLessEqual(len(pk["text"]), 3000)      # hard cap
        # import shows current statuses
        provenance.retract(s, "HF1", "A", reason="obsolete")
        imp = handoff.import_handoff(s, "B", pk["id"])
        self.assertEqual(imp["task"]["id"], "mig")
        statuses = {d["id"]: d["status"] for d in imp["decisions"]}
        self.assertEqual(statuses["HD1"], "tainted")
        self.assertTrue(any(f["status"] == "retracted" for f in imp["findings"]))

    def test_missing_task_or_handoff_raises(self):
        with self.assertRaises(KeyError):
            handoff.export_handoff(self.store, "nope", "A")
        with self.assertRaises(KeyError):
            handoff.import_handoff(self.store, "A", "nope")

    def test_render_is_capped(self):
        pk = {"id": "h", "task": {"id": "t", "status": "open", "goal": "g" * 5000},
              "dependencies": [], "artifacts": [], "decisions": [], "findings": [], "omitted": 0}
        self.assertLessEqual(len(handoff.render_packet(pk, 500)), 500)


if __name__ == "__main__":
    unittest.main()
