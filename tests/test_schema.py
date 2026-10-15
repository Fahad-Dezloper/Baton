import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from baton.graph import queries, schema  # noqa: E402
from baton.graph.client import graph_name  # noqa: E402
from baton.hooks import cli  # noqa: E402


class SchemaTests(unittest.TestCase):
    def test_index_statements_are_create_index(self):
        for stmt in schema.INDEX_STATEMENTS:
            self.assertTrue(stmt.startswith("CREATE INDEX FOR ("), stmt)

    def test_labels_and_relationships_unique(self):
        self.assertEqual(len(schema.LABELS), len(set(schema.LABELS)))
        self.assertEqual(len(schema.REL_TYPES), len(set(schema.REL_TYPES)))

    def test_queries_are_parameterized(self):
        for name, q in queries.ALL.items():
            self.assertIn("$", q, name)

    def test_graph_name_is_sanitized(self):
        self.assertEqual(graph_name("my repo/1"), "baton_my_repo_1")

    def test_hook_cli_fails_open_on_known_commands(self):
        for sub in cli.SUBCOMMANDS:
            self.assertEqual(cli.main([sub]), 0)

    def test_hook_cli_rejects_unknown(self):
        self.assertEqual(cli.main(["nope"]), 2)


if __name__ == "__main__":
    unittest.main()
