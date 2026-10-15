import unittest

from tests.support import GraphCase

from baton.core import decisions, tasks


class DecisionTests(GraphCase):
    def test_other_actors_open_decision_is_a_conflict_but_own_is_not(self):
        decisions.post_decision(self.store, "A", "use sqlite for orders", artifacts=["./shop/db.py"], kind="storage")
        res_b = decisions.check_conflicts(self.store, "B", ["shop/db.py"])
        self.assertTrue(res_b["has_conflicts"])
        self.assertEqual(res_b["decisions"][0]["author"], "A")
        self.assertEqual(res_b["decisions"][0]["kind"], "storage")
        res_a = decisions.check_conflicts(self.store, "A", ["shop/db.py"])
        self.assertFalse(res_a["has_conflicts"])

    def test_unrelated_paths_do_not_conflict(self):
        decisions.post_decision(self.store, "A", "touch config", artifacts=["shop/config.py"])
        self.assertFalse(decisions.check_conflicts(self.store, "B", ["shop/utils.py"])["has_conflicts"])

    def test_live_lease_conflicts_until_it_expires(self):
        tasks.create_task(self.store, "rename db module", touches=["shop/db.py"], task_id="rn")
        tasks.claim_task(self.store, "rn", "A", lease_seconds=60, now=10_000)
        live = decisions.check_conflicts(self.store, "B", ["shop/db.py"], now=10_030)
        self.assertEqual([t["id"] for t in live["leases"]], ["rn"])
        expired = decisions.check_conflicts(self.store, "B", ["shop/db.py"], now=10_100)
        self.assertEqual(expired["leases"], [])

    def test_duplicate_ticket_detected_across_actors(self):
        tasks.create_task(self.store, "Add rate limiting to create_order!", task_id="d1")
        tasks.claim_task(self.store, "d1", "A", now=20_000)
        res = decisions.check_conflicts(
            self.store, "B", [], goal="add RATE limiting to  create_order", task_id="d2", now=20_001
        )
        self.assertEqual([t["id"] for t in res["duplicates"]], ["d1"])
        self.assertFalse(decisions.check_conflicts(self.store, "A", [], goal="add rate limiting to create_order")["duplicates"])

    def test_supersede_replaces_and_inherits_artifacts(self):
        d1 = decisions.post_decision(self.store, "A", "use json", artifacts=["shop/db.py"], kind="storage")
        d2 = decisions.supersede_decision(self.store, "A", d1["id"], "use sqlite instead")
        self.assertEqual(decisions.get_decision(self.store, d1["id"])["status"], "superseded")
        self.assertEqual(decisions.decision_paths(self.store, d2["id"]), ["shop/db.py"])
        texts = [d["text"] for d in decisions.check_conflicts(self.store, "B", ["shop/db.py"])["decisions"]]
        self.assertIn("use sqlite instead", texts)
        self.assertNotIn("use json", texts)

    def test_describe_is_compact_text(self):
        decisions.post_decision(self.store, "A", "move timeout under limits", artifacts=["shop/config.py"], kind="config")
        text = decisions.describe_conflicts(decisions.check_conflicts(self.store, "B", ["shop/config.py"]))
        self.assertIn("config decision by A", text)
        self.assertLess(len(text), 400)


if __name__ == "__main__":
    unittest.main()
