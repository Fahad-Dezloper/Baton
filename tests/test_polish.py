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


class StopCheckTests(GraphCase):
    def setUp(self):
        self._old = os.environ.pop("CLAUDE_PROJECT_DIR", None)

    def tearDown(self):
        if self._old is not None:
            os.environ["CLAUDE_PROJECT_DIR"] = self._old

    def _edit(self, who, path, now):
        from baton.hooks.config import Config
        project = tempfile.mkdtemp()
        os.makedirs(os.path.join(project, os.path.dirname(path)), exist_ok=True)
        open(os.path.join(project, path), "w").write("x = 1\n")
        events.on_post_tool(self.store, {"session_id": who, "cwd": project, "tool_name": "Edit",
                                         "tool_input": {"file_path": os.path.join(project, path)},
                                         "tool_response": {}}, Config(), now=now)

    def test_stop_asks_for_one_recheck_when_others_edited_the_same_file(self):
        from baton.hooks.config import Config
        a, b = "sa-" + uuid.uuid4().hex[:6], "sb-" + uuid.uuid4().hex[:6]
        sessions.begin_session(self.store, a, now=100)
        sessions.begin_session(self.store, b, now=101)
        self._edit(a, "shop/api.py", 110)
        self._edit(b, "shop/api.py", 120)
        cfg = Config()
        cfg.stop_check = True
        out = events.on_stop(self.store, {"session_id": a, "last_assistant_message": "done"}, cfg, now=130)
        self.assertEqual(out["decision"], "block")
        self.assertIn("shop/api.py", out["reason"])
        again = events.on_stop(self.store, {"session_id": a, "stop_hook_active": True}, cfg, now=140)
        self.assertIsNone(again)
        self.assertIsNone(events.on_stop(self.store, {"session_id": a}, cfg, now=150))
        self.assertIsNone(events.on_stop(self.store, {"session_id": "other"}, Config(), now=160))  # off by default

    def test_no_check_when_no_overlap_or_disabled(self):
        from baton.hooks.config import Config
        a = "sc-" + uuid.uuid4().hex[:6]
        sessions.begin_session(self.store, a, now=100)
        self._edit(a, "solo.py", 110)
        self.assertIsNone(events.on_stop(self.store, {"session_id": a}, Config(), now=120))
        cfg = Config()
        cfg.stop_check = False
        self.assertIsNone(events.on_stop(self.store, {"session_id": a}, cfg, now=130))
