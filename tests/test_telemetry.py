"""Frame format checks for the telemetry risk-reduction prototype."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "telemetry"))
import frame


class FrameTest(unittest.TestCase):
    def test_round_trip(self):
        joints = [(0.1 * i, -0.2 * i, 0.5) for i in range(9)]
        wire = frame.encode(frame.pack(42, 123456789, joints))
        self.assertEqual(len(wire), frame.WIRE_SIZE)
        self.assertEqual(wire.count(0), 1)
        seq, t_us, out = frame.unpack(frame.decode(wire[:-1]))
        self.assertEqual((seq, t_us), (42, 123456789))
        for a, b in zip(joints, out):
            for x, y in zip(a, b):
                self.assertAlmostEqual(x, y, places=5)

    def test_corruption_rejected(self):
        wire = bytearray(frame.encode(frame.pack(1, 2, [(1.0, 2.0, 3.0)] * 9)))
        wire[20] ^= 0x01
        with self.assertRaises(ValueError):
            frame.decode(bytes(wire[:-1]))

    def test_cobs_long_runs(self):
        for data in (b"", b"\0", b"\0\0", bytes(range(1, 256)) * 3, b"\x01" * 254 + b"\0"):
            self.assertEqual(frame.cobs_decode(frame.cobs_encode(data)), data)


if __name__ == "__main__":
    unittest.main()
