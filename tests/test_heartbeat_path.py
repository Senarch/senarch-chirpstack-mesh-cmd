"""Decoding a mesh heartbeat's relay path, on both listener paths.

Stdlib only, no border needed:  python3 -m unittest discover -s tests
"""
import importlib.machinery
import importlib.util
import os
import sys
import unittest

sys.dont_write_bytecode = True
_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mesh-cmd")
_loader = importlib.machinery.SourceFileLoader("mesh_cmd", _SCRIPT)
_spec = importlib.util.spec_from_loader("mesh_cmd", _loader)
mesh = importlib.util.module_from_spec(_spec)
_loader.exec_module(mesh)


# A protobuf encoder written apart from the script's, so the test does not
# check the decoder against itself.
def varint(n):
    n &= (1 << 64) - 1          # a negative int32 goes out sign-extended to 64 bits
    out = bytearray()
    while True:
        b, n = n & 0x7F, n >> 7
        out.append(b | 0x80 if n else b)
        if not n:
            return bytes(out)

def ld(field, data):
    return varint(field << 3 | 2) + varint(len(data)) + data

def vi(field, n):
    return varint(field << 3) + varint(n)

def mesh_event(*items, time_s=None):
    """gw.MeshEvent: gateway_id=1, relay_id=2, time=3, events=4."""
    out = ld(1, b"0016c001aabbccdd") + ld(2, b"11223344")
    if time_s is not None:
        out += ld(3, vi(1, time_s))                 # google.protobuf.Timestamp
    return out + b"".join(ld(4, i) for i in items)

def heartbeat(*hops):
    """MeshEventItem{heartbeat=2}, MeshEventHeartbeat{relay_path=4}."""
    path = b"".join(ld(4, ld(1, rid.encode()) + vi(2, rssi) + vi(3, snr))
                    for rid, rssi, snr in hops)
    return ld(2, path)

def proprietary(event_type, payload):
    """MeshEventItem{proprietary=1}, MeshEventProprietary{event_type=1, payload=2}."""
    return ld(1, vi(1, event_type) + ld(2, payload))


# The same three messages serialized by chirpstack-api 4.19 (gw_pb2), to show
# the hand encoder above produces what a border really sends.
REFERENCE = {
    "direct": "0a1030303136633030316161626263636464120831313232333334341a0608808292c90622021200",
    "two_hops": "0a103030313663303031616162626363646412083131323233333434223d123b22170a08"
                "353536363737383810a4ffffffffffffffff01180722200a0839396161626263631092ff"
                "ffffffffffffff0118fbffffffffffffffff01",
    "proprietary": "0a103030313663303031616162626363646412083131323233333434220d0a0b08c80112067570"
                   "3d343573",
}
DIRECT = mesh_event(heartbeat(), time_s=1764000000)
TWO_HOPS = mesh_event(heartbeat(("55667788", -92, 7), ("99aabbcc", -110, -5)))
PROPRIETARY = mesh_event(proprietary(200, b"up=45s"))
TWO_HOPS_PATH = [{"relay_id": "55667788", "rssi": -92, "snr": 7},
                 {"relay_id": "99aabbcc", "rssi": -110, "snr": -5}]


class EncoderTest(unittest.TestCase):
    def test_matches_protobuf(self):
        self.assertEqual(DIRECT.hex(), REFERENCE["direct"])
        self.assertEqual(TWO_HOPS.hex(), REFERENCE["two_hops"])
        self.assertEqual(PROPRIETARY.hex(), REFERENCE["proprietary"])


class DecodeTest(unittest.TestCase):
    def test_heartbeat_heard_directly(self):
        self.assertEqual(mesh.decode_mesh_event(DIRECT),
                         ("11223344", [("heartbeat", None, [])]))

    def test_heartbeat_two_hops_negative_rssi_snr(self):
        self.assertEqual(mesh.decode_mesh_event(TWO_HOPS),
                         ("11223344", [("heartbeat", None, TWO_HOPS_PATH)]))

    def test_proprietary(self):
        self.assertEqual(mesh.decode_mesh_event(PROPRIETARY),
                         ("11223344", [("proprietary", 200, b"up=45s")]))

    def test_local_listener_unwraps_event(self):
        # --local reads gw.Event{mesh=3} from ZMQ; MQTT carries the bare MeshEvent.
        for msg in (DIRECT, TWO_HOPS, PROPRIETARY):
            self.assertEqual(mesh.decode_event_mesh(ld(3, msg)), mesh.decode_mesh_event(msg))

    def test_int32_extremes(self):
        for n in (0, 1, -1, 127, -128, 2**31 - 1, -2**31):
            v, _ = mesh._rv(varint(n), 0)
            self.assertEqual(mesh._int32(v), n)


class FormatTest(unittest.TestCase):
    def test_format_path(self):
        self.assertEqual(mesh.format_path(None), "no heartbeat heard")
        self.assertEqual(mesh.format_path([]), "direct")
        self.assertEqual(mesh.format_path(TWO_HOPS_PATH[:1]), "via 55667788 (-92 dBm, SNR 7)")
        self.assertEqual(mesh.format_path(TWO_HOPS_PATH),
                         "via 55667788 (-92 dBm, SNR 7) -> 99aabbcc (-110 dBm, SNR -5)")


if __name__ == "__main__":
    unittest.main()
