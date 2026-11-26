"""The relays record and the `relays --watch --state-file` file.

Stdlib only, no border needed:  python3 -m unittest discover -s tests
"""
import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest

sys.dont_write_bytecode = True
_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mesh-cmd")
_loader = importlib.machinery.SourceFileLoader("mesh_cmd", _SCRIPT)
_spec = importlib.util.spec_from_loader("mesh_cmd", _loader)
mesh = importlib.util.module_from_spec(_spec)
_loader.exec_module(mesh)

DAY = 24 * 3600
PATH = [{"relay_id": "55667788", "rssi": -92, "snr": 7}]
HEARTBEAT = [("heartbeat", None, PATH)]
DIRECT = [("heartbeat", None, [])]
UPLINK = [("proprietary", 200, b"up=45s")]


class RecordTest(unittest.TestCase):
    def test_later_uplink_keeps_the_path(self):
        relays = {}
        self.assertEqual(mesh.record_relay_message(relays, "11223344", HEARTBEAT, 1000), PATH)
        self.assertIsNone(mesh.record_relay_message(relays, "11223344", UPLINK, 1100))
        self.assertEqual(relays, {"11223344": {
            "last_seen": 1100, "count": 2, "kinds": ["heartbeat", "proprietary"],
            "path": PATH, "path_heard": 1000}})

    def test_newer_heartbeat_replaces_the_path(self):
        relays = {}
        mesh.record_relay_message(relays, "11223344", HEARTBEAT, 1000)
        self.assertEqual(mesh.record_relay_message(relays, "11223344", DIRECT, 1600), [])
        self.assertEqual(relays["11223344"]["path"], [])
        self.assertEqual(relays["11223344"]["path_heard"], 1600)

    def test_no_heartbeat_means_no_path(self):
        relays = {}
        mesh.record_relay_message(relays, "11223344", UPLINK, 1000)
        self.assertIsNone(relays["11223344"]["path"])
        self.assertIsNone(relays["11223344"]["path_heard"])


class StateFileTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.file = os.path.join(self.dir.name, "relays.json")

    def tearDown(self):
        self.dir.cleanup()

    def test_shape(self):
        relays = {}
        mesh.record_relay_message(relays, "11223344", HEARTBEAT, 1000)
        mesh.record_relay_message(relays, "aabbccdd", UPLINK, 1005)
        mesh.write_state(self.file, relays, 1006)
        with open(self.file) as f:
            self.assertEqual(json.load(f), {"updated": 1006, "relays": {
                "11223344": {"last_seen": 1000, "count": 1, "kinds": ["heartbeat"],
                             "path": PATH, "path_heard": 1000},
                "aabbccdd": {"last_seen": 1005, "count": 1, "kinds": ["proprietary"],
                             "path": None, "path_heard": None}}})
        self.assertEqual(os.listdir(self.dir.name), ["relays.json"])   # no temp file left
        self.assertEqual(mesh.load_state(self.file), relays)

    def test_load_missing_or_invalid(self):
        self.assertEqual(mesh.load_state(self.file), {})
        with open(self.file, "w") as f:
            f.write('{"relays": ')                                     # cut short
        self.assertEqual(mesh.load_state(self.file), {})

    def test_expiry(self):
        now = 10 * DAY
        relays = {"old": {"last_seen": now - DAY - 1}, "edge": {"last_seen": now - DAY},
                  "new": {"last_seen": now - 5}}
        self.assertTrue(mesh.prune_state(relays, now))
        self.assertEqual(sorted(relays), ["edge", "new"])
        self.assertFalse(mesh.prune_state(relays, now))


class WatchTest(unittest.TestCase):
    """watch_relays() with a fake clock and a scripted event stream."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.file = os.path.join(self.dir.name, "relays.json")
        self.now = 10 * DAY + 0.0
        self.writes = []
        real_write = mesh.write_state

        def counting_write(path, relays, now):
            self.writes.append(now)
            real_write(path, relays, now)
        self.saved = (mesh.time, mesh.write_state, mesh.stop_requested)
        mesh.time = types.SimpleNamespace(time=lambda: self.now)
        mesh.write_state = counting_write
        mesh.stop_requested = False

    def tearDown(self):
        mesh.time, mesh.write_state, mesh.stop_requested = self.saved
        self.dir.cleanup()

    def at(self, t, msg):
        self.now = 10 * DAY + t
        return msg

    def test_coalesces_writes_and_keeps_known_relays(self):
        # A previous run left two relays; one has not been heard for over a day.
        mesh.write_state(self.file, {
            "11223344": {"last_seen": 10 * DAY - 60, "count": 3, "kinds": ["heartbeat"],
                         "path": [], "path_heard": 10 * DAY - 60},
            "deadbeef": {"last_seen": 10 * DAY - DAY - 60, "count": 1, "kinds": ["proprietary"],
                         "path": None, "path_heard": None}}, 10 * DAY - 60)
        self.writes.clear()

        def stream():
            yield self.at(0.2, ("aabbccdd", HEARTBEAT))
            yield self.at(0.4, ("aabbccdd", UPLINK))      # same second: no write yet
            yield self.at(0.6, ("11223344", UPLINK))
            yield self.at(1.1, None)                        # a quiet second: flush
            yield self.at(1.5, None)                        # nothing new: no write
            yield self.at(1.7, ("11223344", UPLINK))
            mesh.stop_requested = True                      # SIGTERM
            yield self.at(1.8, None)

        self.assertEqual(mesh.watch_relays(stream(), self.file), 0)
        self.assertEqual(self.writes, [10 * DAY, 10 * DAY + 1, 10 * DAY + 1])   # start, flush, exit
        with open(self.file) as f:
            state = json.load(f)
        self.assertEqual(sorted(state["relays"]), ["11223344", "aabbccdd"])     # deadbeef expired
        self.assertEqual(state["relays"]["11223344"], {
            "last_seen": 10 * DAY + 1, "count": 5, "kinds": ["heartbeat", "proprietary"],
            "path": [], "path_heard": 10 * DAY - 60})                         # path kept
        self.assertEqual(state["relays"]["aabbccdd"]["path"], PATH)

    def test_stream_lost_exits_1(self):
        self.assertEqual(mesh.watch_relays(iter([self.at(0, None)]), self.file), 1)


if __name__ == "__main__":
    unittest.main()
