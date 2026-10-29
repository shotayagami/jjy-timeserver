import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jjyd.timesync import SyncMonitor  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
