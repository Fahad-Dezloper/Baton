import os
import subprocess
import tempfile
import unittest
import uuid

from tests.support import GraphCase

from baton import gc as baton_gc
from baton.core import decisions, sessions
from baton.hooks import events
from baton.service import Service, default_workspace


class GcTests(GraphCase):
    def test_removes_old_finished_sessions_and_keeps_live_ones(self):
        s = self.store
        old, live = "old-" + uuid.uuid4().hex[:6], "live-" + uuid.uuid4().hex[:6]
        sessions.begin_session(s, old, now=1000)
        sessions.touch(s, old, "a.py", now=1001)
        sessions.end_session(s, old, now=1002)
        sessions.begin_session(s, live, now=1000)
        res = baton_gc.collect(s, days=1, now=1000 + 10 * 86400)
        self.assertEqual(res["sessions"], 1)
        left = s.rows("MATCH (t:Task) RETURN t.owner", read_only=True)
        self.assertEqual([r[0] for r in left], [live])


class ServiceInputTests(GraphCase):
    def test_unknown_ids_are_rejected(self):
        svc = Service(self.store, base_actor="svc")
        self.assertFalse(svc.create_task("x task", depends_on=["nope"])["ok"])
        self.assertFalse(svc.post_decision("y", based_on=["nope"])["ok"])
        self.assertTrue(svc.create_task("x task")["ok"])

    def test_absolute_paths_match_relative_ones(self):
        root = tempfile.mkdtemp()
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = root
        try:
            svc = Service(self.store, base_actor="svc2")
            svc.post_decision("changed api", artifacts=[os.path.join(root, "src", "a.py")], kind="interface")
            res = decisions.check_conflicts(self.store, "someone-else", ["src/a.py"])
            self.assertTrue(res["has_conflicts"])
        finally:
            if old is None:
                os.environ.pop("CLAUDE_PROJECT_DIR")
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = old


class WorktreeTests(unittest.TestCase):
    def test_worktrees_share_a_workspace(self):
        base = tempfile.mkdtemp()
        main = os.path.join(base, "repo")
        os.makedirs(main)
        run = lambda *a, cwd=main: subprocess.run(a, cwd=cwd, check=True, capture_output=True)
        run("git", "init", "-q")
        run("git", "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "i")
        wt = os.path.join(base, "wt")
        run("git", "worktree", "add", "-q", wt)
        self.assertEqual(default_workspace(main), default_workspace(wt))
        self.assertNotEqual(default_workspace(main), default_workspace(tempfile.mkdtemp()))


class WarningTextTests(unittest.TestCase):
    def test_collision_text_does_not_ask_for_manual_logging(self):
        import inspect
        src = inspect.getsource(events.on_pre_tool)
        self.assertNotIn("post_decision", src)


if __name__ == "__main__":
    unittest.main()
