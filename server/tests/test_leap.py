import sys
import threading
import time
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jjyd.main as M  # noqa: E402
from jjyd.encoder import JST, encode_minute  # noqa: E402
from jjyd.leap import LeapSchedule, parse_leap_seconds_list  # noqa: E402

SAMPLE = """#$ 3928521600
#@ 4102444800
2272060800 10 # 1 Jan 1972 (初期値。差分の起点なので予定には含めない)
2287785600 11 # 挿入
2303683200 12 # 挿入
2319408000 11 # 削除
"""


def sched(sign):
    return LeapSchedule([(datetime(2030, 1, 1, tzinfo=timezone.utc), sign)])


class ParseTest(unittest.TestCase):
    def test_parse(self):
        events, expiry = parse_leap_seconds_list(SAMPLE)
        self.assertEqual([s for _, s in events], [1, 1, -1])
        self.assertEqual(events[0][0], datetime(1972, 7, 1, tzinfo=timezone.utc))
        self.assertEqual(expiry, datetime(2030, 1, 1, tzinfo=timezone.utc))

    def test_real_2017_entry(self):
        events, _ = parse_leap_seconds_list("2272060800 10\n3692217600 37\n")
        self.assertEqual(events[0][0], datetime(2017, 1, 1, tzinfo=timezone.utc))


class LookupTest(unittest.TestCase):
    def test_window_for_insertion(self):
        s = sched(1)  # 2030-01-01 00:00 UTC = 09:00 JST
        self.assertEqual(s.lookup(datetime(2029, 12, 2, 8, 59, tzinfo=JST)), (0, False))
        self.assertEqual(s.lookup(datetime(2029, 12, 2, 9, 0, tzinfo=JST)), (1, False))
        self.assertEqual(s.lookup(datetime(2029, 12, 31, 12, 0, tzinfo=JST)), (1, False))
        self.assertEqual(s.lookup(datetime(2030, 1, 1, 8, 58, tzinfo=JST)), (1, False))
        self.assertEqual(s.lookup(datetime(2030, 1, 1, 8, 59, tzinfo=JST)), (1, True))
        self.assertEqual(s.lookup(datetime(2030, 1, 1, 9, 0, tzinfo=JST)), (0, False))

    def test_year_boundary_previous_month(self):
        s = LeapSchedule([(datetime(2030, 7, 1, tzinfo=timezone.utc), -1)])
        self.assertEqual(s.lookup(datetime(2030, 6, 2, 9, 0, tzinfo=JST))[0], -1)
        self.assertEqual(s.lookup(datetime(2030, 6, 2, 8, 59, tzinfo=JST))[0], 0)

    def test_no_events(self):
        self.assertEqual(LeapSchedule().lookup(datetime(2026, 10, 30, tzinfo=JST)), (0, False))


class FrameTest(unittest.TestCase):
    last = datetime(2030, 1, 1, 8, 59, tzinfo=JST)

    def test_ls_bits(self):
        f = encode_minute(datetime(2029, 12, 20, 10, 20, tzinfo=JST), leap=1)
        self.assertEqual(f[53:55], ["1", "1"])
        f = encode_minute(datetime(2029, 12, 20, 10, 20, tzinfo=JST), leap=-1)
        self.assertEqual(f[53:55], ["1", "0"])
        f = encode_minute(datetime(2029, 12, 20, 10, 20, tzinfo=JST))
        self.assertEqual(f[53:55], ["0", "0"])
        # 15/45 分は 53,54 秒が ST4,ST5 なので LS は載せない
        f = encode_minute(datetime(2029, 12, 20, 10, 15, tzinfo=JST), leap=1, callsign=True)
        self.assertEqual(f[50:56], ["0"] * 6)
        # 呼出符号なし(既定)なら15分も通常フレームなので LS を載せる
        f = encode_minute(datetime(2029, 12, 20, 10, 15, tzinfo=JST), leap=1)
        self.assertEqual(f[53:55], ["1", "1"])

    def test_insertion_minute_has_61_symbols(self):
        f = encode_minute(self.last, leap=1, leap_now=True)
        self.assertEqual(len(f), 61)
        self.assertEqual(f[58:], ["0", "0", "M"])  # 59 秒は 0、P0 は 60 秒
        self.assertEqual(f[53:55], ["1", "1"])
        self.assertEqual([i for i, s in enumerate(f) if s == "M"], [0, 9, 19, 29, 39, 49, 60])

    def test_deletion_minute_has_59_symbols(self):
        f = encode_minute(self.last, leap=-1, leap_now=True)
        self.assertEqual(len(f), 59)
        self.assertEqual(f[58], "M")  # P0 は 58 秒
        self.assertEqual(f[53:55], ["1", "0"])
        self.assertEqual([i for i, s in enumerate(f) if s == "M"], [0, 9, 19, 29, 39, 49, 58])

    def test_default_frame_unchanged(self):
        f = encode_minute(self.last)
        self.assertEqual(len(f), 60)
        self.assertEqual(f[59], "M")


class FileTest(unittest.TestCase):
    def test_load_and_missing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "leap-seconds.list"
            p.write_text("2272060800 10\n3692217600 37\n", encoding="ascii")
            s = LeapSchedule(path=str(p))
            self.assertEqual(len(s.events), 1)
            s.reload_if_changed()  # 変更なしなら何もしない
            self.assertEqual(len(s.events), 1)
        self.assertEqual(LeapSchedule(path=str(Path(d) / "none")).events, [])


class RunLoopTest(unittest.TestCase):
    def test_insertion_sends_61st_second(self):
        """壁時計が UTC 0時に 23:59:59 を繰り返す(カーネルの挿入動作)状況を模擬する。"""
        S = 1_000_000_000
        real = time.time_ns
        base = real()
        start = int(datetime(2029, 12, 31, 23, 59, 55, 300000, tzinfo=timezone.utc).timestamp() * S)
        leap_at = int(datetime(2030, 1, 1, tzinfo=timezone.utc).timestamp() * S)

        def fake():
            v = start + real() - base
            return v - S if v >= leap_at else v

        events = []

        class Tx:
            carrier_on = True

            def set_carrier(self, on):
                pass

            def level(self, full):
                events.append((time.monotonic(), "level", full))

            def key(self, on):
                pass

            def signal(self, on):
                events.append((time.monotonic(), "signal", on))

        class Mon:
            ok = True

        stop = {"flag": False}
        with mock.patch.object(time, "time_ns", fake):
            th = threading.Thread(target=M.run, args=(Tx(), Mon(), stop, None, sched(1)))
            th.start()
            time.sleep(8.0)
            stop["flag"] = True
            th.join()

        highs = [t for t, k, v in events if k == "level" and v is True]
        widths = []
        for t, k, v in events:
            if k == "level" and v is False:
                widths.append(t - [h for h in highs if h <= t][-1])
        # 56,57,58,59 秒, うるう秒(60 秒), 次の分の 0 秒, 1 秒... が 1 秒間隔で並ぶ
        gaps = [b - a for a, b in zip(highs, highs[1:])]
        self.assertGreaterEqual(len(highs), 7)
        for g in gaps[:7]:
            self.assertAlmostEqual(g, 1.0, delta=0.06)
        # 幅: 56 秒=0(0.8)、57 秒=0?、... 59 秒=0(0.8)、60 秒=P0(0.2)、0 秒=M(0.2)
        self.assertAlmostEqual(widths[3], 0.8, delta=0.06)  # 59 秒は 0
        self.assertAlmostEqual(widths[4], 0.2, delta=0.06)  # 60 秒目の P0
        self.assertAlmostEqual(widths[5], 0.2, delta=0.06)  # 次の分の先頭マーカー


if __name__ == "__main__":
    unittest.main()
