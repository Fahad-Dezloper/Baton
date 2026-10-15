import os
import unittest
import uuid

from tests.support import GraphCase
from tests.test_capture import tool_result, tool_use, write_transcript

from baton.capture import derive
from baton.core import decisions
from baton.hooks import events
from baton.hooks.config import Config

PROJECT = "/work/proj"


def post_edit(session, rel, old, new, tool="Edit"):
    """Payload shaped like the host's real post-edit event."""
    fp = os.path.join(PROJECT, rel)
    if tool == "Write":
        resp = {"type": "create" if old is None else "update", "filePath": fp,
                "content": new, "originalFile": old}
        return {"session_id": session, "cwd": PROJECT, "tool_name": "Write",
                "tool_input": {"file_path": fp, "content": new}, "tool_response": resp}
    resp = {"filePath": fp, "oldString": old, "newString": new, "originalFile": old, "replaceAll": False}
    return {"session_id": session, "cwd": PROJECT, "tool_name": "Edit",
            "tool_input": {"file_path": fp, "old_string": old, "new_string": new}, "tool_response": resp}


class CaptureIntegrationTests(GraphCase):
    def setUp(self):
        os.environ["CLAUDE_PROJECT_DIR"] = PROJECT
        self.a = "A-" + uuid.uuid4().hex[:6]
        self.b = "B-" + uuid.uuid4().hex[:6]

    def post(self, payload, cfg=None, now=1_000_000):
        return events.HANDLERS["post-tool"](self.store, payload, cfg or Config(), now=now)

    def test_signature_change_becomes_an_interface_decision_visible_to_others(self):
        old = "def create_order(order_id, items):\n    return 1\n"
        new = "def create_order(order_id, items, client_id):\n    return 1\n"
        self.post(post_edit(self.a, "shop/api.py", old, new))
        events.HANDLERS["session-end"](self.store, {"session_id": self.a}, Config(), now=1_000_001)
        out = events.HANDLERS["pre-tool"](
            self.store,
            {"session_id": self.b, "cwd": PROJECT, "tool_name": "Edit",
             "tool_input": {"file_path": os.path.join(PROJECT, "shop/api.py")}},
            Config(), now=1_000_002,
        )
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("interface decision by", ctx)
        self.assertIn("client_id", ctx)

    def test_repeated_edits_update_one_decision(self):
        v1 = "def f(a):\n    pass\n"
        v2 = "def f(a, b):\n    pass\n"
        v3 = "def f(a, b, c):\n    pass\n"
        self.post(post_edit(self.a, "m1.py", v1, v2), now=1)
        self.post(post_edit(self.a, "m1.py", v2, v3), now=2)
        did = derive.decision_id(self.a, "m1.py", "interface")
        n = self.store.rows("MATCH (d:Decision {id: $id}) RETURN count(d)", {"id": did}, read_only=True)[0][0]
        self.assertEqual(n, 1)
        self.assertIn("f(a, b) -> f(a, b, c)", decisions.get_decision(self.store, did)["text"])

    def test_created_module_and_config_and_dependency(self):
        self.post(post_edit(self.a, "shop/report.py", None, "def order_summary(order_id):\n    pass\n", tool="Write"))
        self.post(post_edit(self.a, "shop/config.py", 'CONFIG = {\n  "a": 1,\n}\n',
                            'CONFIG = {\n  "a": 1,\n  "tax_rate": 0.08,\n}\n'))
        self.post(post_edit(self.a, "shop/db.py", "import os\n", "import os\nimport sqlite3\n"))
        kinds = {
            r[0]
            for r in self.store.rows(
                "MATCH (d:Decision {author: $a, auto: true}) RETURN d.kind", {"a": self.a}, read_only=True
            )
        }
        self.assertEqual(kinds, {"interface", "config", "storage"})

    def test_capture_can_be_disabled(self):
        old, new = "def g(a):\n    pass\n", "def g(a, b):\n    pass\n"
        self.post(post_edit(self.a, "off.py", old, new), cfg=Config(capture=False))
        n = self.store.rows("MATCH (d:Decision {author: $a}) RETURN count(d)", {"a": self.a}, read_only=True)[0][0]
        self.assertEqual(n, 0)

    def test_payload_without_original_content_is_skipped_safely(self):
        p = post_edit(self.a, "x.py", "def h(a):\n    pass\n", "def h(a, b):\n    pass\n")
        p["tool_response"].pop("originalFile")
        self.assertIsNone(self.post(p))
        n = self.store.rows("MATCH (d:Decision {author: $a}) RETURN count(d)", {"a": self.a}, read_only=True)[0][0]
        self.assertEqual(n, 0)

    def test_stop_records_test_verification_in_handoff(self):
        path = write_transcript([
            tool_use("t1", "python3 -m unittest discover"),
            tool_result("t1", "FAILED (failures=1)\n", True),
        ])
        events.HANDLERS["prompt"](self.store, {"session_id": self.a, "prompt": "fix storage bug"}, Config(), now=1)
        events.HANDLERS["stop"](
            self.store,
            {"session_id": self.a, "transcript_path": path, "last_assistant_message": "I changed db.py"},
            Config(), now=2,
        )
        from baton.core import sessions

        row = self.store.rows("MATCH (h:Handoff {id: $id}) RETURN h.summary",
                              {"id": sessions.handoff_id_for(self.a)}, read_only=True)
        self.assertIn("Verification:", row[0][0])
        self.assertIn("failed", row[0][0])
        self.assertIn("unittest discover", row[0][0])


if __name__ == "__main__":
    unittest.main()
