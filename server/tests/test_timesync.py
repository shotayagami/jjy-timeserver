import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jjyd.timesync import SyncMonitor, tracking_ok  # noqa: E402


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def make(state, clock, **kw):
    return SyncMonitor(30, 21600, checker=lambda: False, state_file=state,
                       wall=clock, mono=clock, **kw)


class RtcTest(unittest.TestCase):
    def test_no_rtc_mode_needs_sync(self):
        c = Clock()
        m = make(None, c)
        self.assertFalse(m.evaluate(False))
        self.assertTrue(m.evaluate(True))
        c.t += 21600
        self.assertTrue(m.evaluate(False))
        c.t += 1
        self.assertFalse(m.evaluate(False))  # holdover 超過

    def test_restore_within_holdover(self):
        with tempfile.TemporaryDirectory() as d:
            f = str(Path(d) / "last_sync")
            Path(f).write_text("999000\n")          # 1000 秒前
            c = Clock(1_000_000)
            m = make(f, c, rtc_holdover_s=86400)
            self.assertTrue(m.evaluate(False))     # NTP 未同期でも許可
            c.t += 86400
            self.assertFalse(m.evaluate(False))    # RTC holdover 超過で停止

    def test_reject_old_or_backwards_time(self):
        with tempfile.TemporaryDirectory() as d:
            f = str(Path(d) / "last_sync")
            for last in ("1.0", "2000000"):        # 古すぎる / 未来(RTC が巻き戻った)
                Path(f).write_text(last)
                self.assertFalse(make(f, Clock(1_000_000)).evaluate(False))
            self.assertFalse(make(str(Path(d) / "none"), Clock()).evaluate(False))

    def test_persist_is_throttled(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "last_sync"
            c = Clock(5000)
            m = make(str(f), c)
            m.evaluate(True)
            self.assertEqual(float(f.read_text()), 5000)
            c.t += 60
            m.evaluate(True)
            self.assertEqual(float(f.read_text()), 5000)   # 15分未満は書かない
            c.t += 900
            m.evaluate(True)
            self.assertEqual(float(f.read_text()), 5960)


class TrackingTest(unittest.TestCase):
    TAIL = "1761882134.1,{off},-0.0014,0.0143,12.859,-0.444,34.645,0.0249,0.0018,64.3,{leap}"

    def line(self, refid, stratum, off=0.0022, leap="Normal"):
        return f"{refid},,{stratum}," + self.TAIL.format(off=off, leap=leap)

    def test_synced_to_a_real_source(self):
        self.assertTrue(tracking_ok(self.line("8A0217CE", 3)))

    def test_local_reference_is_not_synced(self):
        # `local stratum 10`: 起動直後でも chrony は stratum 10 の自己参照で「同期済み」に見える
        self.assertFalse(tracking_ok(self.line("7F7F0101", 10)))

    def test_not_synchronised(self):
        self.assertFalse(tracking_ok(self.line("00000000", 0, 0.0, "Not synchronised")))

    def test_clock_still_wrong_before_the_step(self):
        # 実機: 同期先を選んだ後、ステップ補正まで 160 秒ずれていた
        self.assertFalse(tracking_ok(self.line("8A0217CE", 3, -160.5)))
        self.assertTrue(tracking_ok(self.line("8A0217CE", 3, -0.2)))
        self.assertFalse(tracking_ok(self.line("8A0217CE", 3, 0.3)))


if __name__ == "__main__":
    unittest.main()
