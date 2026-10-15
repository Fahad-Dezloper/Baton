import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid

from tests.support import DB_UP, GraphCase

from baton.core import sessions
from baton.graph.client import Store
from baton.hooks import cli, events
from baton.hooks.config import Config, load_config
from baton.service import default_workspace

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
PROJECT = "/work/proj"


def edit(session, rel, agent=None, tool="Edit"):
    p = {"session_id": session, "cwd": PROJECT, "tool_name": tool,
         "tool_input": {"file_path": os.path.join(PROJECT, rel)}}
    if agent:
        p["agent_id"] = agent
    return p


def bash(session, command):
    return {"session_id": session, "cwd": PROJECT, "tool_name": "Bash", "tool_input": {"command": command}}


class PureTests(unittest.TestCase):
    def setUp(self):
        os.environ["CLAUDE_PROJECT_DIR"] = PROJECT

    def test_paths(self):
        self.assertEqual(events.rel_path("/work/proj/shop/db.py", PROJECT), "shop/db.py")
        self.assertEqual(events.rel_path("shop/db.py", PROJECT, cwd=PROJECT), "shop/db.py")
        self.assertIsNone(events.rel_path("/etc/hosts", PROJECT))
        self.assertIsNone(events.rel_path("/work/proj-other/x.py", PROJECT))
        self.assertIsNone(events.rel_path("../outside.py", PROJECT, cwd=PROJECT))

    def test_rename_pairs(self):
        self.assertEqual(events.rename_pairs("git mv shop/db.py shop/store.py"), [("shop/db.py", "shop/store.py")])
        self.assertEqual(events.rename_pairs("cd x && mv -f a.py b.py"), [("a.py", "b.py")])
        self.assertEqual(events.rename_pairs("ls -la"), [])

    def test_edit_paths_filters_outside_and_other_tools(self):
        self.assertEqual(events.edit_paths(edit("s", "a/b.py"), PROJECT), ["a/b.py"])
        self.assertEqual(events.edit_paths({"tool_name": "Read", "tool_input": {"file_path": "/work/proj/x"}}, PROJECT), [])
        self.assertEqual(events.edit_paths(bash("s", "mv a.py b.py"), PROJECT), ["a.py", "b.py"])

    def test_actor_distinguishes_subagents(self):
        self.assertEqual(events.actor_from({"session_id": "S1"}), "S1")
        self.assertEqual(events.actor_from({"session_id": "S1", "agent_id": "abcdef0123456"}), "S1/abcdef01")

    def test_config_defaults_file_and_env(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(load_config(d), Config())
            with open(os.path.join(d, ".baton.json"), "w") as f:
                json.dump({"policy": "deny", "lease_seconds": 120}, f)
            c = load_config(d)
            self.assertEqual((c.policy, c.lease_seconds), ("deny", 120))
            os.environ["BATON_POLICY"] = "nonsense"
            try:
                self.assertEqual(load_config(d).policy, "warn")
            finally:
                del os.environ["BATON_POLICY"]
            os.environ["BATON_DISABLED"] = "1"
            try:
                self.assertFalse(load_config(d).enabled)
            finally:
                del os.environ["BATON_DISABLED"]


class HandlerTests(GraphCase):
    cfg = Config()

    def setUp(self):
        os.environ["CLAUDE_PROJECT_DIR"] = PROJECT
        self.a = "A-" + uuid.uuid4().hex[:6]
        self.b = "B-" + uuid.uuid4().hex[:6]

    def run_ev(self, name, payload, cfg=None, now=1_000_000):
        return events.HANDLERS[name](self.store, payload, cfg or self.cfg, now=now)

    def test_edit_by_one_session_warns_the_other_once(self):
        self.run_ev("session-start", {"session_id": self.a})
        self.run_ev("prompt", {"session_id": self.a, "prompt": "move storage to sqlite"})
        self.assertIsNone(self.run_ev("pre-tool", edit(self.a, "shop/db.py")))   # nothing yet
        self.run_ev("post-tool", edit(self.a, "shop/db.py"))
        out = self.run_ev("pre-tool", edit(self.b, "shop/db.py"), now=1_000_030)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Possible collision on shop/db.py", ctx)
        self.assertIn("move storage to sqlite", ctx)
        self.assertIn("last edit 30s ago", ctx)
        self.assertNotIn("permissionDecision", out["hookSpecificOutput"])
        # same warning is not repeated
        self.assertIsNone(self.run_ev("pre-tool", edit(self.b, "shop/db.py"), now=1_000_040))
        # the editor itself is never warned about its own work
        self.assertIsNone(self.run_ev("pre-tool", edit(self.a, "shop/db.py"), now=1_000_050))

    def test_policy_deny_and_ask(self):
        a, b = "A-" + uuid.uuid4().hex[:6], "B-" + uuid.uuid4().hex[:6]
        self.run_ev("post-tool", edit(a, "shop/cfg.py"))
        deny = self.run_ev("pre-tool", edit(b, "shop/cfg.py"), cfg=Config(policy="deny"))
        self.assertEqual(deny["hookSpecificOutput"]["permissionDecision"], "deny")
        ask = self.run_ev("pre-tool", edit("C-" + uuid.uuid4().hex[:6], "shop/cfg.py"), cfg=Config(policy="ask"))
        self.assertEqual(ask["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_lease_expires_and_session_end_releases(self):
        a, b = "A-" + uuid.uuid4().hex[:6], "B-" + uuid.uuid4().hex[:6]
        self.run_ev("post-tool", edit(a, "shop/x.py"), now=2_000_000)
        self.assertIsNotNone(self.run_ev("pre-tool", edit(b, "shop/x.py"), now=2_000_100))
        # lease (900 s) has expired
        self.assertIsNone(self.run_ev("pre-tool", edit("D-" + uuid.uuid4().hex[:6], "shop/x.py"), now=2_001_000))
        # explicit end releases immediately
        c, e = "C-" + uuid.uuid4().hex[:6], "E-" + uuid.uuid4().hex[:6]
        self.run_ev("post-tool", edit(c, "shop/y.py"), now=3_000_000)
        self.run_ev("session-end", {"session_id": c}, now=3_000_001)
        self.assertIsNone(self.run_ev("pre-tool", edit(e, "shop/y.py"), now=3_000_002))

    def test_duplicate_goal_is_flagged(self):
        a, b = "A-" + uuid.uuid4().hex[:6], "B-" + uuid.uuid4().hex[:6]
        self.run_ev("prompt", {"session_id": a, "prompt": "Add rate limiting to create_order."})
        out = self.run_ev("prompt", {"session_id": b, "prompt": "add RATE limiting to create_order"})
        self.assertIn("same goal", out["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(self.run_ev("prompt", {"session_id": a, "prompt": "something else entirely"}))

    def test_rename_via_bash_is_recorded_and_conflicts(self):
        a, b = "A-" + uuid.uuid4().hex[:6], "B-" + uuid.uuid4().hex[:6]
        self.run_ev("post-tool", bash(a, "git mv shop/db.py shop/store.py"))
        out = self.run_ev("pre-tool", edit(b, "shop/store.py"))
        self.assertIn("rename decision", out["hookSpecificOutput"]["additionalContext"])

    def test_subagents_conflict_with_each_other(self):
        s = "S-" + uuid.uuid4().hex[:6]
        self.run_ev("post-tool", edit(s, "shop/z.py", agent="aaaaaaaa11"))
        out = self.run_ev("pre-tool", edit(s, "shop/z.py", agent="bbbbbbbb22"))
        self.assertIsNotNone(out)

    def test_stop_exports_idempotent_handoff_and_next_session_gets_briefing(self):
        a, b = "A-" + uuid.uuid4().hex[:6], "B-" + uuid.uuid4().hex[:6]
        self.run_ev("prompt", {"session_id": a, "prompt": "make order storage durable"})
        self.run_ev("post-tool", edit(a, "shop/db.py"))
        self.run_ev("stop", {"session_id": a, "last_assistant_message": "Switched db.py to sqlite; tests pass."})
        self.run_ev("stop", {"session_id": a, "last_assistant_message": "Switched db.py to sqlite; tests pass."})
        n = self.store.rows("MATCH (h:Handoff {id: $id}) RETURN count(h)",
                            {"id": sessions.handoff_id_for(a)}, read_only=True)[0][0]
        self.assertEqual(n, 1)
        self.run_ev("session-end", {"session_id": a})
        out = self.run_ev("session-start", {"session_id": b})
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("make order storage durable", ctx)
        self.assertIn("Switched db.py to sqlite", ctx)
        self.assertLessEqual(len(ctx), sessions.BRIEFING_MAX_CHARS)

    def test_session_start_is_silent_when_there_is_nothing_to_say(self):
        fresh = Store("quiet_" + uuid.uuid4().hex[:6])
        try:
            fresh.bootstrap()
            self.assertIsNone(events.on_session_start(fresh, {"session_id": "only-me"}, Config(), now=1))
        finally:
            fresh.drop()


class CliTests(unittest.TestCase):
    def run_cli(self, event, payload, env_extra=None):
        env = {**os.environ, "PYTHONPATH": SRC, "BATON_CONNECT_TIMEOUT": "1", "BATON_QUERY_TIMEOUT": "3"}
        env.update(env_extra or {})
        return subprocess.run([sys.executable, "-B", "-m", "baton.hooks.cli", event],
                              input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=30)

    def test_unknown_event_is_usage_error(self):
        self.assertEqual(cli.main(["nope"]), 2)
        self.assertEqual(cli.main([]), 2)

    def test_known_events_exit_zero_with_garbage_input(self):
        os.environ["BATON_DISABLED"] = "1"
        try:
            for ev in cli.SUBCOMMANDS:
                self.assertEqual(cli.main([ev], stdin=io.StringIO("not json")), 0)
        finally:
            del os.environ["BATON_DISABLED"]

    @unittest.skipUnless(DB_UP, "FalkorDB not reachable")
    def test_end_to_end_subprocess_warns_second_session(self):
        proj = tempfile.mkdtemp(prefix="baton_proj_")
        ws = default_workspace(proj)
        env = {"CLAUDE_PROJECT_DIR": proj}
        try:
            fp = os.path.join(proj, "app.py")
            r1 = self.run_cli("post-tool", {"session_id": "S-one", "cwd": proj, "tool_name": "Write",
                                             "tool_input": {"file_path": fp}}, env)
            self.assertEqual((r1.returncode, r1.stdout), (0, ""))
            r2 = self.run_cli("pre-tool", {"session_id": "S-two", "cwd": proj, "tool_name": "Write",
                                            "tool_input": {"file_path": fp}}, env)
            self.assertEqual(r2.returncode, 0)
            out = json.loads(r2.stdout)
            self.assertIn("Possible collision on app.py", out["hookSpecificOutput"]["additionalContext"])
            self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        finally:
            Store(ws).drop()

    def test_fails_open_when_store_is_down(self):
        r = self.run_cli("pre-tool", {"session_id": "S", "cwd": "/tmp", "tool_name": "Write",
                                       "tool_input": {"file_path": "/tmp/x.py"}},
                         {"BATON_FALKORDB_PORT": "6399", "CLAUDE_PROJECT_DIR": "/tmp"})
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_disabled_does_nothing(self):
        r = self.run_cli("session-start", {"session_id": "S"},
                         {"BATON_DISABLED": "1", "BATON_FALKORDB_PORT": "6399", "CLAUDE_PROJECT_DIR": "/tmp"})
        self.assertEqual((r.returncode, r.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
