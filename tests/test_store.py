import unittest
import uuid

from tests.support import DB_UP, GraphCase, Store

from baton.core.paths import normalize_path, normalize_paths


class PathTests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(normalize_path("./shop//db.py"), "shop/db.py")
        self.assertEqual(normalize_path("shop\\db.py"), "shop/db.py")
        self.assertEqual(normalize_path("/abs/x.py"), "abs/x.py")
        self.assertEqual(normalize_paths(["a.py", "./a.py", "b.py"]), ["a.py", "b.py"])


class BootstrapTests(GraphCase):
    def test_bootstrap_is_idempotent(self):
        self.store.bootstrap()
        self.store.bootstrap()
        names = {r[0] for r in self.store.rows("CALL db.indexes() YIELD label RETURN label")}
        self.assertTrue({"Task", "Decision", "Artifact"} <= names)


@unittest.skipUnless(DB_UP, "FalkorDB not reachable")
class IsolationCanary(unittest.TestCase):
    """A fact written in workspace A must never be visible from workspace B."""

    def test_workspaces_are_isolated(self):
        a = Store("iso_a_" + uuid.uuid4().hex[:6])
        b = Store("iso_b_" + uuid.uuid4().hex[:6])
        try:
            a.query("CREATE (:Decision {id: 'canary', text: 'tenant-a-secret'})")
            self.assertEqual(len(a.rows("MATCH (d:Decision) RETURN d")), 1)
            self.assertEqual(b.rows("MATCH (n) RETURN n"), [])
            self.assertNotEqual(a.graph_name, b.graph_name)
        finally:
            a.drop()
            b.drop()

    def test_hostile_workspace_names_stay_inside_prefix(self):
        s = Store("../../etc/passwd; DROP")
        self.assertTrue(s.graph_name.startswith("baton_"))
        self.assertNotIn("/", s.graph_name)
        self.assertNotIn(" ", s.graph_name)


if __name__ == "__main__":
    unittest.main()
