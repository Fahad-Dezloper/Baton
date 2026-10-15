import threading
import unittest

from tests.support import GraphCase

from baton.core import tasks


class TaskTests(GraphCase):
    def test_create_and_dependencies_gate_ready_frontier(self):
        a = tasks.create_task(self.store, "build storage layer", task_id="ta")
        b = tasks.create_task(self.store, "export orders", depends_on=["ta"], task_id="tb")
        ready = {t["id"] for t in tasks.ready_tasks(self.store)}
        self.assertIn("ta", ready)
        self.assertNotIn("tb", ready)
        r = tasks.claim_task(self.store, "tb", "w1")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "blocked")
        self.assertEqual(r.blockers[0]["id"], "ta")
        self.assertTrue(tasks.claim_task(self.store, "ta", "w1").ok)
        self.assertTrue(tasks.complete_task(self.store, "ta", "w1"))
        self.assertTrue(tasks.claim_task(self.store, "tb", "w2").ok)

    def test_claim_reasons(self):
        tasks.create_task(self.store, "t reasons", task_id="tr")
        self.assertEqual(tasks.claim_task(self.store, "nope", "w").reason, "not_found")
        self.assertTrue(tasks.claim_task(self.store, "tr", "w1", now=1000).ok)
        held = tasks.claim_task(self.store, "tr", "w2", now=1001)
        self.assertFalse(held.ok)
        self.assertEqual((held.reason, held.holder), ("held", "w1"))
        tasks.complete_task(self.store, "tr", "w1", now=1002)
        self.assertEqual(tasks.claim_task(self.store, "tr", "w2", now=1003).reason, "done")

    def test_expired_lease_can_be_taken_over(self):
        tasks.create_task(self.store, "lease expiry", task_id="te")
        self.assertTrue(tasks.claim_task(self.store, "te", "w1", lease_seconds=10, now=1000).ok)
        self.assertFalse(tasks.claim_task(self.store, "te", "w2", now=1005).ok)
        taken = tasks.claim_task(self.store, "te", "w2", now=1011)
        self.assertTrue(taken.ok)
        self.assertEqual(taken.task["owner"], "w2")
        # the old owner can no longer renew, complete or release
        self.assertFalse(tasks.renew_lease(self.store, "te", "w1", now=1012))
        self.assertFalse(tasks.complete_task(self.store, "te", "w1", now=1012))
        self.assertFalse(tasks.release_task(self.store, "te", "w1"))

    def test_renew_complete_release_only_by_owner(self):
        tasks.create_task(self.store, "owner only", task_id="to")
        tasks.claim_task(self.store, "to", "w1", lease_seconds=10, now=2000)
        self.assertFalse(tasks.renew_lease(self.store, "to", "w2", now=2001))
        self.assertTrue(tasks.renew_lease(self.store, "to", "w1", lease_seconds=100, now=2005))
        self.assertTrue(tasks.release_task(self.store, "to", "w1"))
        self.assertTrue(tasks.claim_task(self.store, "to", "w2", now=2006).ok)

    def test_concurrent_claims_have_exactly_one_winner(self):
        workers = 24
        for round_no in range(20):
            tid = "race%d" % round_no
            tasks.create_task(self.store, "race %d" % round_no, task_id=tid)
            barrier = threading.Barrier(workers)
            wins = []

            def work(i):
                from baton.graph.client import Store

                s = Store(self.ws)
                barrier.wait()
                if tasks.claim_task(s, tid, "w%d" % i, now=5000).ok:
                    wins.append(i)

            ts = [threading.Thread(target=work, args=(i,)) for i in range(workers)]
            [t.start() for t in ts]
            [t.join() for t in ts]
            self.assertEqual(len(wins), 1, "round %d winners=%s" % (round_no, wins))
            self.assertEqual(tasks.get_task(self.store, tid)["version"], 1)


if __name__ == "__main__":
    unittest.main()
