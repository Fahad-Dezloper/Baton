"""Shared helpers for integration tests that need a live FalkorDB."""

import os
import sys
import unittest
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from baton.graph.client import Store  # noqa: E402


def db_available() -> bool:
    try:
        s = Store("probe_" + uuid.uuid4().hex[:6])
        s.query("RETURN 1")
        s.drop()
        return True
    except Exception:
        return False


DB_UP = db_available()


class GraphCase(unittest.TestCase):
    """Each test class gets its own throwaway workspace graph."""

    @classmethod
    def setUpClass(cls):
        if not DB_UP:
            raise unittest.SkipTest("FalkorDB not reachable on localhost:6379")
        cls.ws = "t_" + uuid.uuid4().hex[:10]
        cls.store = Store(cls.ws)
        cls.store.bootstrap()

    @classmethod
    def tearDownClass(cls):
        if DB_UP:
            cls.store.drop()
