import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jjyd.encoder import JST, MARKER_SECONDS, MORSE_UNIT, callsign_keying, encode_minute  # noqa: E402


def val(f, weights_start_widths):
    """[(start, width), ...] を連結したビット列を整数にする。"""
    v = 0
    for start, width in weights_start_widths:
        for b in f[start:start + width]:
            v = v * 2 + int(b)
    return v


def decode(f):
    return dict(
        minute=val(f, [(1, 3)]) * 10 + val(f, [(5, 4)]),
        hour=val(f, [(12, 2)]) * 10 + val(f, [(15, 4)]),
        yday=val(f, [(22, 2)]) * 100 + val(f, [(25, 4)]) * 10 + val(f, [(30, 4)]),
        year=val(f, [(41, 4)]) * 10 + val(f, [(45, 4)]),
        wday=val(f, [(50, 3)]),
    )


class EncoderTest(unittest.TestCase):
    def test_roundtrip_and_structure(self):
        for dt in [
            datetime(2026, 10, 29, 12, 34, tzinfo=JST),
            datetime(2024, 12, 31, 23, 59, tzinfo=JST),  # うるう年 366日目
            datetime(2000, 1, 1, 0, 0, tzinfo=JST),
        ]:
            f = encode_minute(dt)
            self.assertEqual(len(f), 60)
            self.assertEqual([i for i, s in enumerate(f) if s == "M"], list(MARKER_SECONDS))
            d = decode(f)
            self.assertEqual(d["minute"], dt.minute)
            self.assertEqual(d["hour"], dt.hour)
            self.assertEqual(d["yday"], dt.timetuple().tm_yday)
            self.assertEqual(d["year"], dt.year % 100)
            self.assertEqual(d["wday"], (dt.weekday() + 1) % 7)
            # パリティ(偶数): ビット群+パリティの1の数が偶数
            self.assertEqual(sum(int(x) for x in f[12:19]) % 2, int(f[36]))
            self.assertEqual(sum(int(x) for x in f[1:9]) % 2, int(f[37]))
            for z in (4, 10, 11, 14, 20, 21, 24, 34, 35, 38, 40, 53, 54, 55, 56, 57, 58):
                self.assertEqual(f[z], "0", f"sec {z}")

    def test_known_frame(self):
        # 2026-10-29(木) 12:34 JST, 通算日302
        f = "".join(encode_minute(datetime(2026, 10, 29, 12, 34, tzinfo=JST)))
        self.assertEqual(f[0:10], "M011" + "0" + "0100" + "M")  # 分=34
        self.assertEqual(f[10:20], "000100010M")  # 時=12

    def test_utc_input_is_converted(self):
        from datetime import timezone
        a = encode_minute(datetime(2026, 10, 29, 3, 34, tzinfo=timezone.utc))
        b = encode_minute(datetime(2026, 10, 29, 12, 34, tzinfo=JST))
        self.assertEqual(a, b)


class CallsignTest(unittest.TestCase):
    def test_normal_minute_has_no_callsign(self):
        f = encode_minute(datetime(2004, 4, 1, 17, 25, tzinfo=JST), callsign=True)
        self.assertNotIn("C", f)
        self.assertEqual(f[50:53], ["1", "0", "0"])  # 木曜

    def test_callsign_is_off_by_default(self):
        # 既定では15・45分も通常フレーム: 呼出符号なし、年・曜日が入る
        for minute in (15, 45):
            f = encode_minute(datetime(2004, 4, 1, 17, minute, tzinfo=JST))
            self.assertNotIn("C", f)
            self.assertEqual(f, encode_minute(datetime(2004, 4, 1, 17, minute, tzinfo=JST), callsign=False))
            d = decode(f)
            self.assertEqual((d["year"], d["wday"]), (4, 4))

    def test_callsign_minutes_frame(self):
        # 2004-04-01 17:15 は NICT ページの図(呼出符号送出時)と同じ日時
        for minute in (15, 45):
            f = encode_minute(datetime(2004, 4, 1, 17, minute, tzinfo=JST), callsign=True)
            self.assertEqual(f[40:49], ["C"] * 9)
            self.assertEqual(f[39], "M")  # P4
            self.assertEqual(f[49], "M")  # P5
            self.assertEqual(f[50:59], ["0"] * 9)  # ST1〜ST6 と 56〜58 秒(曜日・LS は送らない)
            self.assertEqual(f[59], "M")
            self.assertEqual(f[38], "0")
            # 年(41〜48 秒)は呼出符号に置き換わるので送らない。分・時・通算日は通常どおり
            self.assertEqual(val(f, [(1, 3)]) * 10 + val(f, [(5, 4)]), minute)
            self.assertEqual(val(f, [(12, 2)]) * 10 + val(f, [(15, 4)]), 17)
            self.assertEqual(val(f, [(22, 2)]) * 100 + val(f, [(25, 4)]) * 10 + val(f, [(30, 4)]), 92)
            self.assertEqual(sum(int(x) for x in f[1:9]) % 2, int(f[37]))

    def test_callsign_keying_matches_measured_pattern(self):
        # 40.0〜49.0 秒 = 111 単位: 余白7 + JJY(45) + 語間7 + JJY(45) + 余白7(実測: 約 570ms ずつ)
        k = callsign_keying()
        lens = [round((b - a) / MORSE_UNIT) for a, b in k]
        j, y = [1, 3, 3, 3], [3, 1, 3, 3]
        self.assertEqual(lens, (j + j + y) * 2)
        self.assertAlmostEqual(MORSE_UNIT, 0.0811, places=4)
        self.assertAlmostEqual(k[0][0], 0.5676, places=3)         # 最初の余白
        self.assertAlmostEqual(9.0 - k[-1][1], 0.5676, places=3)  # 最後の余白(49.0 秒まで)
        self.assertAlmostEqual(k[12][0] - k[11][1], 0.5676, places=3)  # 二語の間隔(Y と次の J の間)
        self.assertAlmostEqual(k[-1][1] - k[0][0], 9.0 - 14 * MORSE_UNIT, places=5)
        self.assertTrue(all(a2 > b1 for (_, b1), (a2, _) in zip(k, k[1:])))


if __name__ == "__main__":
    unittest.main()
