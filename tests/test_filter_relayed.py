"""set-filter-relayed: catalog entry, usage text and argument checking.

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


class FilterRelayed(unittest.TestCase):
    def test_catalog_has_type_153(self):
        match = [c for c in mesh.load_catalog() if c["name"] == "set-filter-relayed"]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]["type"], 153)
        self.assertEqual(match[0]["params"][0]["values"], ["on", "off"])

    def test_usage_lists_it(self):
        out = subprocess.run([sys.executable, _SCRIPT, "--help"], capture_output=True, text=True).stdout
        self.assertIn("set-filter-relayed <relay_id> on|off", out)

    def test_state_must_be_on_or_off(self):
        r = subprocess.run([sys.executable, _SCRIPT, "set-filter-relayed", "11223344", "yes"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("invalid choice", r.stderr)


if __name__ == "__main__":
    unittest.main()
