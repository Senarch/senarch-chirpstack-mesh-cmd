"""The usage text names the relays listen time and how to change it.

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


class RelaysUsage(unittest.TestCase):
    def test_usage_names_for_and_its_default(self):
        text = mesh._USAGE_COMMANDS
        self.assertIn("relays [--for <s>]", text)
        self.assertIn("1230 s", text)
        self.assertIn("10 min", text)

    def test_relays_help_prints_it(self):
        out = subprocess.run([sys.executable, _SCRIPT, "relays", "--help"],
                             capture_output=True, text=True).stdout
        self.assertIn("relays [--for <s>]", out)
        self.assertIn("1230 s", out)

    def test_default_listen_covers_two_heartbeats(self):
        self.assertEqual(mesh.RELAYS_LISTEN_S, 2 * 600 + 30)


if __name__ == "__main__":
    unittest.main()
