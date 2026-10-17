import os
import tempfile
import unittest
import uuid

from tests.support import GraphCase

from baton.capture import derive
from baton.core import decisions, sessions
from baton.hooks import events
from baton.hooks.config import Config
from baton.graph.client import Store


def project_with(files):
    root = tempfile.mkdtemp(prefix="baton_v2_")
    for rel, text in files.items():
        full = os.path.join(root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(text)
    return root


def edit_payload(session, project, rel, tool="Edit"):
    return {"session_id": session, "cwd": project, "tool_name": tool,
            "tool_input": {"file_path": os.path.join(project, rel)}}


class LocalImportTests(unittest.TestCase):
    def test_own_package_is_not_a_new_dependency(self):
        old, new = "import os\n", "import os\nfrom shop import db\nimport requests\n"
        d = derive.derive_decisions("shop/api.py", old, new, local_modules={"shop"})
        self.assertEqual([x["kind"] for x in d], ["other"])
        self.assertIn("requests", d[0]["text"])
        self.assertNotIn("shop", d[0]["text"].replace("shop/api.py", ""))


class DesignationTests(GraphCase):
    def test_earliest_session_proceeds_and_ties_break_by_id(self):
        s = self.store
        first, second = "F-" + uuid.uuid4().hex[:6], "S-" + uuid.uuid4().hex[:6]
        sessions.begin_session(s, first, now=100)
        sessions.begin_session(s, second, now=200)
        d_first = {"created_at": 100, "owner": first}
        d_second = {"created_at": 200, "owner": second}
        self.assertTrue(sessions.designated_session(s, first, [d_second]))
        self.assertFalse(sessions.designated_session(s, second, [d_first]))
        # equal start time: smaller id wins on both sides
        a, b = "a-" + uuid.uuid4().hex[:6], "b-" + uuid.uuid4().hex[:6]
        sessions.begin_session(s, a, now=300)
        sessions.begin_session(s, b, now=300)
        self.assertTrue(sessions.designated_session(s, a, [{"created_at": 300, "owner": b}]))
        self.assertFalse(sessions.designated_session(s, b, [{"created_at": 300, "owner": a}]))


class BriefingTests(GraphCase):
    def test_sessions_without_a_prompt_are_not_worth_a_briefing(self):
        fresh = Store("brief_" + uuid.uuid4().hex[:6])
        try:
            fresh.bootstrap()
            sessions.begin_session(fresh, "other", now=1000)           # no prompt yet
            sessions.begin_session(fresh, "me", now=1001)
            self.assertEqual(sessions.briefing(fresh, "me", now=1002), "")
            sessions.set_goal(fresh, "other", "make storage durable", now=1003)
            self.assertIn("make storage durable", sessions.briefing(fresh, "me", now=1004))
        finally:
            fresh.drop()


class NearbyChangesTests(GraphCase):
    def setUp(self):
        self.a = "A-" + uuid.uuid4().hex[:6]
        self.b = "B-" + uuid.uuid4().hex[:6]

    def test_new_file_in_same_package_sees_others_interface_changes(self):
        proj = project_with({"shop/models.py": "x = 1\n", "other/util.py": "y = 1\n"})
        os.environ["CLAUDE_PROJECT_DIR"] = proj
        decisions.upsert_decision(self.store, self.a, "dec_n1", "Order gains discount_percent field",
                                  artifacts=["shop/models.py"], kind="interface", now=5000)
        decisions.upsert_decision(self.store, self.a, "dec_n2", "util changed", artifacts=["other/util.py"],
                                  kind="interface", now=5000)
        out = events.on_pre_tool(self.store, edit_payload(self.b, proj, "shop/report.py", "Write"),
                                 Config(), now=5010)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("recently changed files related to shop/report.py", ctx)
        self.assertIn("discount_percent", ctx)
        self.assertNotIn("util changed", ctx)           # different directory, not imported
        self.assertNotIn("Possible collision", ctx)     # not a same-file collision

    def test_imported_module_in_another_directory_is_related(self):
        proj = project_with({"app/main.py": "from lib import core\n", "lib/core.py": "z = 1\n",
                             "lib/__init__.py": ""})
        os.environ["CLAUDE_PROJECT_DIR"] = proj
        decisions.upsert_decision(self.store, self.a, "dec_n3", "core.run() now takes a flag",
                                  artifacts=["lib/core.py"], kind="interface", now=6000)
        out = events.on_pre_tool(self.store, edit_payload(self.b, proj, "app/main.py"), Config(), now=6010)
        self.assertIn("core.run() now takes a flag", out["hookSpecificOutput"]["additionalContext"])

    def test_old_notes_and_own_changes_are_ignored(self):
        proj = project_with({"shop/models.py": "x = 1\n"})
        os.environ["CLAUDE_PROJECT_DIR"] = proj
        decisions.upsert_decision(self.store, self.a, "dec_n4", "stale", artifacts=["shop/models.py"],
                                  kind="interface", now=100)
        decisions.upsert_decision(self.store, self.a, "dec_n5", "just a note", artifacts=["shop/models.py"],
                                  kind="note", now=7000)
        decisions.upsert_decision(self.store, self.b, "dec_n6", "mine", artifacts=["shop/models.py"],
                                  kind="interface", now=7000)
        out = events.on_pre_tool(self.store, edit_payload(self.b, proj, "shop/report.py", "Write"),
                                 Config(), now=7010)
        self.assertIsNone(out)

    def test_same_file_collision_still_reported_and_not_duplicated(self):
        proj = project_with({"shop/api.py": "x = 1\n"})
        os.environ["CLAUDE_PROJECT_DIR"] = proj
        decisions.upsert_decision(self.store, self.a, "dec_n7", "create_order gains client_id",
                                  artifacts=["shop/api.py"], kind="interface", now=8000)
        out = events.on_pre_tool(self.store, edit_payload(self.b, proj, "shop/api.py"), Config(), now=8010)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Possible collision on shop/api.py", ctx)
        self.assertEqual(ctx.count("create_order gains client_id"), 1)


class ClipGoalTests(unittest.TestCase):
    def test_keeps_the_end_of_a_long_goal(self):
        from baton.core.tasks import clip_goal
        text = "Shared preamble. " * 30 + "Ticket B: add stock reservation."
        out = clip_goal(text, 160)
        self.assertLessEqual(len(out), 160)
        self.assertTrue(out.endswith("add stock reservation."))
        self.assertEqual(clip_goal("short", 160), "short")


if __name__ == "__main__":
    unittest.main()
