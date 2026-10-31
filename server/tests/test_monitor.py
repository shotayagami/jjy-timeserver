import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jjyd import main as M  # noqa: E402
from datetime import datetime  # noqa: E402

from jjyd.encoder import JST, PULSE_WIDTH, callsign_keying, encode_minute  # noqa: E402
from jjyd.status import StatusWriter  # noqa: E402
from jjyd.timesync import SyncMonitor  # noqa: E402
from jjymon import data, emulate, frame as fr  # noqa: E402

FRAME = "M" + "10" * 29 + "M"  # 60 シンボル。1 秒目 = '1'、2 秒目 = '0'


class EmulateTest(unittest.TestCase):
    def test_pulse_widths_and_leds(self):
        base = 60 * 1000  # idx 0
        for idx, sym in ((0, "M"), (1, "1"), (2, "0")):
            w = PULSE_WIDTH[sym]
            hi = emulate.at(FRAME, base + idx + w - 0.01, True)
            lo = emulate.at(FRAME, base + idx + w + 0.01, True)
            self.assertEqual((hi.sym, hi.amplitude, hi.d1, hi.d2), (sym, 1.0, True, False))
            self.assertEqual((lo.amplitude, lo.d1, lo.d2), (0.1, False, True))
            self.assertTrue(lo.d3)

    def test_second_start_is_high(self):
        s = emulate.at(FRAME, 60 * 1000 + 5.0, True)
        self.assertEqual((s.idx, s.sym, s.amplitude, s.d1), (5, FRAME[5], 1.0, True))

    def test_muted_or_unknown(self):
        s = emulate.at(FRAME, 60 * 1000 + 1.1, False)
        self.assertEqual((s.amplitude, s.d1, s.d2), (0.0, False, False))
        self.assertEqual(emulate.at(None, 60 * 1000 + 0.1, True).sym, "M")  # フレーム不明でも 0 秒目はマーカー
        s = emulate.at(None, 60 * 1000 + 3.1, True)
        self.assertEqual((s.sym, s.amplitude), (None, 0.0))

    def test_callsign_follows_keying(self):
        frame = ["M"] * 60
        for i in range(40, 49):
            frame[i] = "C"
        frame = "".join(frame)
        a, b = callsign_keying()[0]
        on = emulate.at(frame, 60 * 1000 + 40 + (a + b) / 2, True)
        off = emulate.at(frame, 60 * 1000 + 40 + a / 2, True)
        self.assertEqual((on.amplitude, on.d1, on.d2), (1.0, True, False))
        self.assertEqual((off.amplitude, off.d1, off.d2), (0.0, True, True))


class SegmentsTest(unittest.TestCase):
    def check(self, frame, idx):
        sym = frame[idx]
        segs = emulate.segments(sym, idx, True)
        self.assertEqual(segs[0][0], 0.0)
        for i, (off, amp, d1, d2) in enumerate(segs):  # 各区間の始めと終わり直前で、at() と同じ値
            end = segs[i + 1][0] if i + 1 < len(segs) else 1.0
            for ph in (off + 1e-6, end - 1e-6):
                s = emulate.at(frame, 60 * 1000 + idx + ph, True)
                self.assertEqual((s.amplitude, s.d1, s.d2), (amp, d1, d2), (idx, ph))

    def test_matches_at(self):
        for idx in (0, 1, 2, 9, 30):
            self.check(FRAME, idx)
        call = ["M"] * 60
        for i in range(40, 49):
            call[i] = "C"
        for idx in range(40, 49):
            self.check("".join(call), idx)

    def test_muted_and_unknown_are_flat(self):
        self.assertEqual(emulate.segments("1", 3, False), [(0.0, 0.0, False, False)])
        self.assertEqual(emulate.segments(None, 3, True), [(0.0, 0.0, False, False)])
        self.assertEqual([o for o, *_ in emulate.segments("0", 3, True)], [0.0, PULSE_WIDTH["0"]])


class FrameTest(unittest.TestCase):
    def test_decode_matches_encoder(self):
        for dt in (datetime(2026, 10, 31, 13, 49, tzinfo=JST), datetime(2000, 1, 1, 0, 0, tzinfo=JST),
                   datetime(2099, 12, 31, 23, 59, tzinfo=JST), datetime(2024, 2, 29, 7, 8, tzinfo=JST)):
            d = fr.decode("".join(encode_minute(dt)))
            self.assertEqual((d["min"], d["hour"], d["doy"], d["year"]), (dt.minute, dt.hour, dt.timetuple().tm_yday, dt.year))
            self.assertEqual(d["wday"], (dt.weekday() + 1) % 7)
            self.assertTrue(d["pa1_ok"] and d["pa2_ok"])
            self.assertEqual((d["su"], d["ls"]), ((0, 0), (0, 0)))

    def test_leap_warning(self):
        t = datetime(2026, 6, 30, 8, 0, tzinfo=JST)
        self.assertEqual(fr.decode("".join(encode_minute(t, 1)))["ls"], (1, 1))
        self.assertEqual(fr.decode("".join(encode_minute(t, -1)))["ls"], (1, 0))

    def test_callsign_frame(self):
        frame = "".join(encode_minute(datetime(2026, 10, 31, 13, 15, tzinfo=JST), callsign=True))
        self.assertTrue(fr.is_callsign(frame))
        d = fr.decode(frame)
        self.assertEqual((d["min"], d["hour"], d["year"], d["wday"], d["ls"]), (15, 13, None, None, None))
        lay = fr.layout(True)
        self.assertEqual((lay[44][0], lay[50], lay[55]), ("call", ("st", "ST1"), ("st", "ST6")))

    def test_callsign_minutes_can_be_changed_for_tests(self):
        every20 = (0, 20, 40)
        for minute, expect in ((0, True), (20, True), (40, True), (15, False), (45, False)):
            f = "".join(encode_minute(datetime(2026, 10, 31, 14, minute, tzinfo=JST), callsign=True, callsign_minutes=every20))
            self.assertEqual(fr.is_callsign(f), expect, minute)
        f = "".join(encode_minute(datetime(2026, 10, 31, 14, 15, tzinfo=JST), callsign=True))  # 既定は 15・45 分
        self.assertTrue(fr.is_callsign(f))

    def test_layout_covers_every_second_and_weights_sum(self):
        lay = fr.layout()
        self.assertEqual(set(lay), set(range(61)))
        self.assertEqual([lay[i][1] for i in range(1, 9)], ["40", "20", "10", "", "8", "4", "2", "1"])
        self.assertEqual((lay[0], lay[59], lay[36], lay[53]), (("mk", "M"), ("mk", "P0"), ("par", "PA1"), ("ls", "LS1")))


class DataTest(unittest.TestCase):
    def test_parse_sources_real_output(self):
        text = ("^,+,2001:df0:232:eea0::fff3,1,6,377,1,0.001298273,0.001298273,0.010219793\n"
                "^,*,133.243.238.163,1,6,377,1,0.000422872,0.000422872,0.009444815\n")
        s = data.parse_sources(text)
        self.assertEqual((s[1]["state"], s[1]["name"], s[1]["stratum"], s[1]["reach"]), ("*", "133.243.238.163", 1, 0o377))
        self.assertAlmostEqual(s[0]["offset"], 0.001298273)

    def test_parse_tracking(self):
        t = data.parse_tracking("85F3EEA3,133.243.238.163,2,1788000000.1,-0.0002,0.0001,0.0003,1.5,0.01,0.02,0.01,0.02,64.0,Normal")
        self.assertEqual((t["stratum"], t["leap"], t["ref"]), (2, "Normal", "133.243.238.163"))
        self.assertAlmostEqual(t["offset"], -0.0002)

    def test_read_status_stale_and_broken(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "status.json"
            self.assertIsNone(data.read_status(str(p)))
            p.write_text("{broken")
            self.assertIsNone(data.read_status(str(p)))
            p.write_text(json.dumps({"time": 1000.0, "carrier": True}))
            self.assertEqual(data.read_status(str(p), 1005.0)["carrier"], True)
            self.assertIsNone(data.read_status(str(p), 1000.0 + data.STALE_S + 1))


class StatusTest(unittest.TestCase):
    def test_writer_is_atomic_and_gives_up(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            w = StatusWriter(str(p))
            w.write({"a": 1})
            self.assertEqual(json.loads(p.read_text()), {"a": 1})
            self.assertFalse(Path(str(p) + ".tmp").exists())
            bad = StatusWriter(str(Path(d) / "no" / "such" / "s.json"))
            for _ in range(5):
                bad.write({"a": 1})
            self.assertEqual(bad.fails, 3)  # 3 回で諦める

    def test_sync_status(self):
        t = [1000.0]
        m = SyncMonitor(30, 21600, checker=lambda: False, wall=lambda: t[0], mono=lambda: t[0])
        self.assertEqual(m.status()["age_s"], None)
        m.evaluate(True)
        t[0] += 12.34
        st = m.status()
        self.assertEqual((st["ok"], st["age_s"], st["limit_s"], st["mode"]), (False, 12.3, 21600, "ntp"))  # ok は run() が更新する

    def test_send_pulse_reports_edges(self):
        class Tx:
            def __getattr__(self, name):
                return lambda *a: None
        start = time.time_ns()
        rise, fall = M.send_pulse(Tx(), "M", start)
        self.assertGreaterEqual(rise, 0)
        self.assertAlmostEqual(fall, 200.0, delta=30)


if __name__ == "__main__":
    unittest.main()
