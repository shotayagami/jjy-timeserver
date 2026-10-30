import sys
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jjyd import main as M  # noqa: E402
from jjyd.encoder import JST, LED_ON_SECONDS, PULSE_WIDTH, encode_minute  # noqa: E402
from jjyd.lcd import Lcd, format_lines  # noqa: E402


class FakeBus:
    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(bytes(data))

    def close(self):
        pass


class LcdTest(unittest.TestCase):
    def test_format(self):
        dt = datetime(2026, 10, 30, 8, 5, 9, tzinfo=JST)
        l1, l2 = format_lines(dt, 60, "TX")
        self.assertEqual(l1, "2026-10-30 Fri  ")
        self.assertEqual(l2, "08:05:09 60k TX ")
        self.assertTrue(all(len(x) == 16 for x in (l1, l2)))

    def test_init_and_show(self):
        bus = FakeBus()
        lcd = Lcd(bus, contrast=32, sleep=lambda s: None)
        cmds = [w[1] for w in bus.writes if w[0] == 0x00]
        self.assertEqual(cmds[:3], [0x38, 0x39, 0x14])
        self.assertEqual(cmds[3], 0x70 | (32 & 0x0F))
        self.assertEqual(cmds[4], 0x56 | ((32 >> 4) & 3))
        self.assertEqual(cmds[-2:], [0x0C, 0x01])
        bus.writes.clear()
        lcd.show("A" * 16, "B" * 16)
        self.assertEqual(bus.writes[0], bytes([0x00, 0x80]))
        self.assertEqual(bus.writes[1], bytes([0x40]) + b"A" * 16)
        self.assertEqual(bus.writes[2], bytes([0x00, 0xC0]))  # 2 行目 = DDRAM 0x40
        self.assertEqual(bus.writes[3], bytes([0x40]) + b"B" * 16)


class LedRuleTest(unittest.TestCase):
    def test_on_durations(self):
        self.assertEqual(LED_ON_SECONDS["1"], 0.5)   # ビット1: 0.5 秒点灯
        self.assertEqual(LED_ON_SECONDS["0"], 0.2)   # ビット0: 短く点灯して消灯
        self.assertEqual(LED_ON_SECONDS["M"], 0.8)   # マーカー

    def test_run_loop_drives_led_after_high_pulse(self):
        events = []

        class Tx:
            carrier_on = True

            def set_carrier(self, on):
                self.carrier_on = on

            def level(self, full):
                events.append((time.time_ns(), "level", full))

            def key(self, on):
                pass

            def signal(self, on):
                events.append((time.time_ns(), "signal", on))

        class Mon:
            ok = True

        class Lcd_:
            def __init__(self):
                self.shown = []

            def show(self, a, b):
                self.shown.append((a, b))

        lcd = Lcd_()
        stop = {"flag": False}
        th = threading.Thread(target=M.run, args=(Tx(), Mon(), stop, M.Display(lcd, 60)))
        th.start()
        time.sleep(3.3)
        stop["flag"] = True
        th.join()

        S = 1e9
        checked = 0
        for i, (t, kind, v) in enumerate(events):
            if not (kind == "level" and v is True):
                continue
            boundary = round(t / S) * S
            sym = encode_minute(datetime.fromtimestamp(boundary / S, JST))[int(boundary / S) % 60]
            if sym == "C":  # 呼出符号秒は別テスト(CallsignTest)で確認
                continue
            nxt = [e for e in events[i:] if e[1] == "signal" and e[2] is True]
            if not nxt:
                continue
            on_at = (nxt[0][0] - boundary) / S
            self.assertAlmostEqual(on_at, PULSE_WIDTH[sym], delta=0.04)  # 高レベルが終わった直後に点灯
            checked += 1
        self.assertGreaterEqual(checked, 2)
        # 点灯後は次の秒頭で消灯している
        offs = [e for e in events if e[1] == "signal" and e[2] is False]
        self.assertTrue(offs)
        self.assertTrue(lcd.shown and lcd.shown[0][1].endswith("TX "))


if __name__ == "__main__":
    unittest.main()
