import argparse
import logging
import os
import signal
import time
import tomllib
from datetime import datetime

from .encoder import JST, PULSE_WIDTH, encode_minute
from .lcd import DryRunLcd, Lcd, LinuxI2C, format_lines
from .timesync import SyncMonitor, rtc_present
from .transmitter import DryRunTransmitter, Transmitter

log = logging.getLogger("jjyd")
S = 1_000_000_000
MAX_LATE_NS = 50_000_000  # 秒境界から50ms以上遅れたらその秒は送らない


def sleep_until(target_ns: int) -> None:
    """粗くsleepし、最後の約2msはビジーウェイトで合わせる。"""
    while True:
        rem = target_ns - time.time_ns()
        if rem <= 0:
            return
        if rem > 3_000_000:
            time.sleep((rem - 2_000_000) / 1e9)


class Display:
    """LCD 表示。失敗しても送信は止めない(3回続けて失敗したら表示だけ諦める)。"""

    def __init__(self, lcd, khz: int):
        self.lcd, self.khz, self.fails = lcd, khz, 0

    def update(self, dt: datetime, state: str) -> None:
        if self.lcd is None:
            return
        try:
            self.lcd.show(*format_lines(dt, self.khz, state))
            self.fails = 0
        except Exception as e:  # I2C の一時的なエラー
            self.fails += 1
            log.warning("LCD write failed (%d): %s", self.fails, e)
            if self.fails >= 3:
                log.error("LCD disabled after repeated failures")
                self.lcd = None


def run(tx, monitor: SyncMonitor, stop: dict, display: Display | None = None) -> None:
    display = display or Display(None, 0)
    cur_minute, frame = None, None
    while not stop["flag"]:
        boundary = (time.time_ns() // S + 1) * S
        sleep_until(boundary)
        if time.time_ns() - boundary > MAX_LATE_NS:
            log.warning("missed second boundary, skipping")
            continue
        now = datetime.fromtimestamp(boundary // S, JST)

        if monitor.ok != tx.carrier_on:
            tx.set_carrier(monitor.ok)
        if not monitor.ok:
            tx.signal(False)
            display.update(now, "OFF")
            continue

        minute = boundary // (60 * S)
        if minute != cur_minute:
            t = datetime.fromtimestamp(minute * 60, JST)
            frame, cur_minute = encode_minute(t), minute
            log.info("frame %s JST", t.strftime("%Y-%m-%d %H:%M (%a)"))
        sym = frame[(boundary // S) % 60]
        tx.signal(False)  # 高レベル(最大振幅)の間は消灯
        tx.level(True)
        sleep_until(boundary + int(PULSE_WIDTH[sym] * S))
        tx.level(False)
        tx.signal(True)  # 低レベルの間(次の秒頭まで)点灯: ビット1=0.5s、ビット0=0.2s、マーカー=0.8s
        display.update(now, "TX")  # 信号の立ち下がり後に書く(送信タイミングを乱さない)


def main() -> None:
    ap = argparse.ArgumentParser(description="JJY time code transmitter")
    ap.add_argument("-c", "--config", default="/etc/jjyd.toml")
    ap.add_argument("--dry-run", action="store_true", help="GPIO を使わずログだけ出す")
    ap.add_argument("--print-frame", action="store_true", help="現在の分のフレームを表示して終了")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    if args.print_frame:
        f = encode_minute(datetime.now(JST))
        print(" ".join("".join(f[i:i + 10]) for i in range(0, 60, 10)))
        return

    cfg = {}
    if os.path.exists(args.config):
        with open(args.config, "rb") as fp:
            cfg = tomllib.load(fp)
    c, lv, ts = cfg.get("carrier", {}), cfg.get("level", {}), cfg.get("timesync", {})
    rtc, sg, lcd_cfg = cfg.get("rtc", {}), cfg.get("signal", {}), cfg.get("lcd", {})

    state_file = None
    if rtc.get("enabled", False):
        if rtc_present() or args.dry_run:
            state_file = rtc.get("state_file", "/var/lib/jjyd/last_sync")
        else:
            log.warning("[rtc] enabled but /sys/class/rtc/rtc0 not found; RTC mode ignored")
    monitor = SyncMonitor(ts.get("check_interval_s", 30), ts.get("holdover_s", 21600),
                          state_file=state_file, rtc_holdover_s=rtc.get("holdover_s", 86400))
    khz = c.get("khz", 60)
    lcd = None
    if args.dry_run:
        monitor.checker = lambda: True
        tx = DryRunTransmitter()
        if lcd_cfg.get("enabled", False):
            lcd = DryRunLcd()
    else:
        tx = Transmitter(khz, c.get("pwm_chip", 0), c.get("pwm_channel", 0), lv.get("gpio", 23),
                         select_gpio=c.get("select_gpio"), signal_gpio=sg.get("gpio"))
        if lcd_cfg.get("enabled", False):
            try:
                lcd = Lcd(LinuxI2C(lcd_cfg.get("bus", 1), lcd_cfg.get("address", 0x3E)), lcd_cfg.get("contrast", 32))
            except Exception as e:  # LCD が無くても送信は続ける
                log.warning("LCD not available: %s", e)
        try:  # 可能ならリアルタイム優先度
            os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(20))
        except (PermissionError, AttributeError, OSError):
            log.warning("SCHED_FIFO unavailable; timing jitter may be larger")

    stop = {"flag": False}
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.update(flag=True))

    monitor.start()
    try:
        run(tx, monitor, stop, Display(lcd, khz))
    finally:
        if lcd is not None:
            lcd.close()
        tx.close()


if __name__ == "__main__":
    main()
