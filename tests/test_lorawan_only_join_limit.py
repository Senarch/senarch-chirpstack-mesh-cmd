"""set-lorawan-only (157) and set-join-limit (158): catalog entries, usage text and argument checking.

Stdlib only, no border needed:  python3 -m unittest discover -s tests
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mesh-cmd")
_loader = importlib.machinery.SourceFileLoader("mesh_cmd", _SCRIPT)
_spec = importlib.util.spec_from_loader("mesh_cmd", _loader)
mesh = importlib.util.module_from_spec(_spec)
_loader.exec_module(mesh)


def run(*argv):
    return subprocess.run([sys.executable, _SCRIPT, *argv], capture_output=True, text=True)


class LorawanOnlyJoinLimit(unittest.TestCase):
    def test_catalog_has_157_and_158(self):
        cat = {c["name"]: c for c in mesh.load_catalog()}
        self.assertEqual(cat["set-lorawan-only"]["type"], 157)
        self.assertEqual(cat["set-lorawan-only"]["params"][0]["values"], ["on", "off"])
        self.assertEqual(cat["set-join-limit"]["type"], 158)
        self.assertEqual((cat["set-join-limit"]["params"][0]["min"], cat["set-join-limit"]["params"][0]["max"]), (0, 100))

    def test_usage_lists_them(self):
        out = run("--help").stdout
        self.assertIn("set-lorawan-only <relay_id> on|off", out)
        self.assertIn("set-join-limit <relay_id> <n>", out)

    def test_lorawan_only_state_must_be_on_or_off(self):
        r = run("set-lorawan-only", "11223344", "maybe")
        self.assertEqual(r.returncode, 2)
        self.assertIn("invalid choice", r.stderr)

    def test_join_limit_range(self):
        for bad in ("101", "-1"):
            r = run("set-join-limit", "11223344", bad)
            self.assertNotEqual(r.returncode, 0, bad)
            self.assertIn("0-100", r.stderr + r.stdout, bad)

    def test_join_limit_must_be_a_number(self):
        r = run("set-join-limit", "11223344", "four")
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
