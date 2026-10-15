import json
import os
import tempfile
import unittest

from baton.capture import derive, signatures, transcript


class SignatureTests(unittest.TestCase):
    def test_python_public_signatures_only(self):
        src = "def a(x, y):\n    pass\n\nasync def b():\n    pass\n\ndef _hidden(z):\n    pass\n\nclass K(Base):\n    pass\n"
        s = signatures.signatures(src, "m.py")
        self.assertEqual(set(s), {"a", "b", "K"})
        self.assertEqual(s["a"], "a(x, y)")

    def test_multiline_params_are_normalized(self):
        s = signatures.signatures("def f(a,\n      b=1):\n    pass\n", "m.py")
        self.assertEqual(s["f"], "f(a, b=1)")

    def test_js_forms(self):
        src = ("export function one(a, b) {}\nexport const two = async (x) => x\n"
               "class Three {}\nconst four = (q) => q\n")
        self.assertEqual(set(signatures.signatures(src, "m.ts")), {"one", "two", "Three", "four"})

    def test_unsupported_extension_is_empty(self):
        self.assertEqual(signatures.signatures("def a(): pass", "notes.txt"), {})

    def test_diff(self):
        old = {"a": "a(x)", "b": "b()"}
        new = {"a": "a(x, y)", "c": "c()"}
        changed, added, removed = signatures.diff_signatures(old, new)
        self.assertEqual((changed, added, removed), ([("a(x)", "a(x, y)")], ["c()"], ["b()"]))

    def test_python_imports_skip_stdlib_but_keep_storage(self):
        src = "import os\nimport sqlite3\nfrom requests import get\nimport json, redis\nfrom . import local\n"
        self.assertEqual(signatures.imports(src, "m.py"), {"sqlite3", "requests", "redis"})

    def test_js_imports(self):
        src = ("import x from 'lodash'\nimport {y} from './local'\nconst pg = require('pg')\n"
               "import p from '@prisma/client/extras'\nimport fs from 'node:fs'\n")
        self.assertEqual(signatures.imports(src, "m.js"), {"lodash", "pg", "@prisma/client"})


class DeriveTests(unittest.TestCase):
    def test_interface_change_is_reported(self):
        old = "def create_order(order_id, items):\n    pass\n"
        new = "def create_order(order_id, items, client_id):\n    pass\n"
        d = derive.derive_decisions("shop/api.py", old, new)
        self.assertEqual([x["kind"] for x in d], ["interface"])
        self.assertIn("create_order(order_id, items) -> create_order(order_id, items, client_id)", d[0]["text"])

    def test_body_only_change_is_not_a_decision(self):
        old = "def f(x):\n    return x\n"
        new = "def f(x):\n    return x + 1\n"
        self.assertEqual(derive.derive_decisions("a.py", old, new), [])

    def test_config_keys(self):
        old = 'CONFIG = {\n    "currency": "USD",\n    "timeout_seconds": 30,\n}\n'
        new = 'CONFIG = {\n    "currency": "USD",\n    "limits": {"timeout_seconds": 30},\n    "log_level": "INFO",\n}\n'
        d = derive.derive_decisions("shop/config.py", old, new)
        self.assertIn("config", [x["kind"] for x in d])
        text = [x for x in d if x["kind"] == "config"][0]["text"]
        self.assertIn("timeout_seconds", text)
        self.assertIn("log_level", text)

    def test_added_storage_and_dependency(self):
        old = "import os\n"
        new = "import os\nimport sqlite3\nimport requests\n"
        kinds = {x["kind"]: x["text"] for x in derive.derive_decisions("shop/db.py", old, new)}
        self.assertIn("sqlite3", kinds["storage"])
        self.assertIn("requests", kinds["other"])

    def test_new_module_announces_its_api(self):
        d = derive.derive_decisions("shop/report.py", None, "def order_summary(order_id):\n    pass\n")
        self.assertEqual(d[0]["kind"], "interface")
        self.assertIn("order_summary(order_id)", d[0]["text"])

    def test_tests_and_identical_and_huge_are_ignored(self):
        self.assertEqual(derive.derive_decisions("tests/test_x.py", "", "def a(): pass\n"), [])
        self.assertEqual(derive.derive_decisions("a.py", "def a(): pass\n", "def a(): pass\n"), [])
        self.assertEqual(derive.derive_decisions("a.py", None, "x" * (derive.MAX_BYTES + 1)), [])

    def test_decision_ids_are_stable_per_actor_path_kind(self):
        a = derive.decision_id("s1", "a.py", "interface")
        self.assertEqual(a, derive.decision_id("s1", "a.py", "interface"))
        self.assertNotEqual(a, derive.decision_id("s2", "a.py", "interface"))
        self.assertNotEqual(a, derive.decision_id("s1", "a.py", "config"))

    def test_new_text_reconstruction(self):
        self.assertEqual(derive.new_text_for_edit("Write", {"content": "N"}, {"content": "N"}, None), "N")
        self.assertEqual(derive.new_text_for_edit("Edit", {"old_string": "a", "new_string": "b"}, {}, "aXa"), "bXa")
        self.assertEqual(
            derive.new_text_for_edit("Edit", {"old_string": "a", "new_string": "b", "replace_all": True}, {}, "aXa"),
            "bXb",
        )
        edits = [{"old_string": "a", "new_string": "b"}, {"old_string": "b", "new_string": "c"}]
        self.assertEqual(derive.new_text_for_edit("MultiEdit", {"edits": edits}, {}, "a"), "c")
        self.assertIsNone(derive.new_text_for_edit("Edit", {"old_string": "a", "new_string": "b"}, {}, None))


def write_transcript(records, raw_tail=""):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as f:
        for r in records:
            f.write((r if isinstance(r, str) else json.dumps(r)) + "\n")
        f.write(raw_tail)
    return path


def tool_use(i, command):
    return {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "thinking", "thinking": "..."},
        {"type": "tool_use", "id": i, "name": "Bash", "input": {"command": command}}]}}


def tool_result(i, text, error=False):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": i, "content": text, "is_error": error}]}}


class TranscriptTests(unittest.TestCase):
    def test_failed_then_passed_uses_the_latest_run(self):
        path = write_transcript([
            {"type": "user", "message": {"role": "user", "content": "do it"}},
            {"type": "queue-operation", "operation": "x"},
            tool_use("t1", "python3 -m unittest"),
            tool_result("t1", "FAILED (failures=2)\n", True),
            "this line is not json {",
            tool_use("t2", "ls -la"),
            tool_result("t2", "file.py"),
            tool_use("t3", "python3 -m unittest discover"),
            tool_result("t3", "Ran 12 tests in 0.2s\n\nOK"),
        ])
        run = transcript.last_test_run(transcript.read_records(path))
        self.assertEqual((run["status"], run["summary"]), ("passed", "OK"))
        self.assertIn("unittest discover", run["command"])

    def test_failure_detected_from_text_and_list_content(self):
        path = write_transcript([
            tool_use("a", "pytest -q"),
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "a",
                 "content": [{"type": "text", "text": "2 failed, 5 passed in 1s"}]}]}},
        ])
        self.assertEqual(transcript.last_test_run(transcript.read_records(path))["status"], "failed")

    def test_no_test_command_or_missing_file(self):
        path = write_transcript([tool_use("a", "ls"), tool_result("a", "x")])
        self.assertIsNone(transcript.last_test_run(transcript.read_records(path)))
        self.assertEqual(transcript.read_records("/nonexistent/file.jsonl"), [])
        self.assertEqual(transcript.read_records(None), [])

    def test_unfinished_call_without_result_is_skipped(self):
        path = write_transcript([tool_use("a", "pytest")])
        self.assertIsNone(transcript.last_test_run(transcript.read_records(path)))

    def test_tail_read_drops_the_cut_first_line(self):
        recs = [tool_use("t%d" % i, "pytest") for i in range(200)] + [tool_result("t199", "3 passed")]
        path = write_transcript(recs)
        out = transcript.read_records(path, max_bytes=2000)
        self.assertTrue(0 < len(out) < len(recs))


if __name__ == "__main__":
    unittest.main()
