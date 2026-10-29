import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jjyd.encoder import JST, MARKER_SECONDS, encode_minute  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
