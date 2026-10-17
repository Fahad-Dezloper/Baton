import os
import tempfile
import unittest

from baton import doctor


class DoctorPureTests(unittest.TestCase):
    def test_python_version(self):
        self.assertTrue(doctor.check_python((3, 12, 0))[0])
        ok, _, fix = doctor.check_python((3, 8, 1))
        self.assertFalse(ok)
        self.assertIn("3.10", fix)

    def test_missing_package_has_fix(self):
        ok, _, fix = doctor.check_package("definitely_not_a_module_xyz", "somepkg")
        self.assertFalse(ok)
        self.assertEqual(fix, "pip install somepkg")

    def test_plugin_files(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(doctor.check_plugin_files(d)[0])
            for f in doctor.PLUGIN_FILES:
                p = os.path.join(d, f)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                open(p, "w").close()
                os.chmod(p, 0o755)
            self.assertTrue(doctor.check_plugin_files(d)[0])
            os.chmod(os.path.join(d, "bin/baton-hook"), 0o644)
            self.assertFalse(doctor.check_plugin_files(d)[0])

    def test_real_plugin_dir_is_complete(self):
        root = os.path.join(os.path.dirname(__file__), "..", "plugin")
        self.assertTrue(doctor.check_plugin_files(root)[0])

    def test_unreachable_server(self):
        ok, msg, fix = doctor.check_falkordb("127.0.0.1", 1)
        self.assertFalse(ok)
        self.assertIn("docker compose up -d", fix)

    def test_format_and_exit_code(self):
        text, good = doctor.format_results([(True, "a", ""), (False, "b", "do x")])
        self.assertFalse(good)
        self.assertIn("PASS  a", text)
        self.assertIn("FAIL  b\n      fix: do x", text)
        self.assertTrue(doctor.format_results([(True, "a", "")])[1])


if __name__ == "__main__":
    unittest.main()
