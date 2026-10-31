import argparse
import logging
import os
import signal
import time
import tomllib
from datetime import datetime

from .encoder import CALLSIGN_START, JST, PULSE_WIDTH, callsign_keying, encode_minute
from .leap import DEFAULT_PATH, LeapSchedule
from .lcd import DryRunLcd, Lcd, LinuxI2C, format_lines
from .status import DEFAULT_PATH as STATUS_PATH, StatusWriter
from .timesync import SyncMonitor, rtc_present
from .transmitter import DryRunTransmitter, Transmitter

log = logging.getLogger("jjyd")
S = 1_000_000_000
MAX_LATE_NS = 50_000_000  # 秒境界から50ms以上遅れたらその秒は送らない


def sleep_until(target_ns: int, clock=None) -> None:
    """粗くsleepし、最後の約2msはビジーウェイトで合わせる。clock 省略時は壁時計(time.time_ns)。"""
    clock = clock or time.time_ns
    while True:
        rem = target_ns - clock()
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


def send_callsign_second(tx, boundary: int, k: int, keying: list[tuple[float, float]]) -> None:
    """呼出符号の k 秒目(40 秒を 0 とする)を送る。最大振幅のまま搬送波だけを 0%/100% で切替える。"""
    tx.level(True)
    tx.key(False)
    tx.signal(True)
    for a, b in keying:
        if b <= k or a >= k + 1:
            continue
        sleep_until(boundary + int((max(a, k) - k) * S))
        tx.key(True)
        tx.signal(False)
        sleep_until(boundary + int((min(b, k + 1) - k) * S))
        tx.key(False)
        tx.signal(True)


def send_pulse(tx, sym: str, start: int, clock=None) -> tuple[float, float]:
    """start(clock の ns)から sym の幅だけ最大振幅にして、10% に戻す。

    戻り値: 実際に立ち上げた時刻と立ち下げた時刻の、start からの遅れ [ms](モニタ表示用)。
    """
    clock = clock or time.time_ns
    tx.signal(False)  # 高レベル(最大振幅)の間は消灯
    tx.level(True)
    rise = clock()
    tx.key(True)  # 呼出符号の直後に搬送波を戻す(通常は何もしない)
    sleep_until(start + int(PULSE_WIDTH[sym] * S), clock)
    tx.level(False)
    fall = clock()
    tx.signal(True)  # 低レベルの間(次の秒頭まで)点灯: ビット1=0.5s、ビット0=0.2s、マーカー=0.8s
    return (rise - start) / 1e6, (fall - start) / 1e6


def run(tx, monitor: SyncMonitor, stop: dict, display: Display | None = None,
        leap: LeapSchedule | None = None, callsign: bool = False, status: StatusWriter | None = None,
        khz: int = 0) -> None:
    display = display or Display(None, 0)
    cur_minute, frame = None, None
    minute_label = ""

    def publish(boundary: int, idx: int | None = None, sym: str | None = None,
                edges: tuple[float, float] | None = None) -> None:
        """この秒の状態をモニタへ渡す。frame/minute は送信中のみ(止まっている間は null)。"""
        if status is None:
            return
        status.write({
            "version": 1, "pid": os.getpid(), "time": time.time(), "second": boundary // S, "khz": khz,
            "carrier": tx.carrier_on, "sync": monitor.status(),
            "minute": minute_label if tx.carrier_on else None,
            "frame": "".join(frame) if tx.carrier_on and frame else None,
            "idx": idx, "sym": sym,
            "rise_ms": None if edges is None else round(edges[0], 3),
            "fall_ms": None if edges is None else round(edges[1], 3),
        })

    keying = callsign_keying()
    while not stop["flag"]:
        boundary = (time.time_ns() // S + 1) * S
        sleep_until(boundary)
        late = time.time_ns() - boundary
        mono0 = time.monotonic_ns() - late  # この秒頭の単調時計。うるう秒挿入中は壁時計が戻るので使う
        if late > MAX_LATE_NS:
            log.warning("missed second boundary, skipping")
            continue
        now = datetime.fromtimestamp(boundary // S, JST)

        if monitor.ok != tx.carrier_on:
            tx.set_carrier(monitor.ok)
        if not monitor.ok:
            tx.signal(False)
            display.update(now, "OFF")
            publish(boundary)
            continue

        minute = boundary // (60 * S)
        if minute != cur_minute:
            t = datetime.fromtimestamp(minute * 60, JST)
            warn, last = 0, False
            if leap is not None:
                leap.reload_if_changed()
                warn, last = leap.lookup(t)
            frame, cur_minute = encode_minute(t, warn, last, callsign), minute
            minute_label = t.strftime("%Y-%m-%d %H:%M")
            if len(frame) != 60:
                log.warning("leap second %s at the end of this minute", "insertion" if len(frame) > 60 else "deletion")
            log.info("frame %s JST", t.strftime("%Y-%m-%d %H:%M (%a)"))
        idx = (boundary // S) % 60
        if idx >= len(frame):  # うるう秒削除の分で壁時計が進まなかった場合
            continue
        sym = frame[idx]
        if sym == "C":  # 毎時15・45分の呼出符号
            send_callsign_second(tx, boundary, idx - CALLSIGN_START, keying)
            continue  # キーオフが秒境界の直前になる秒があるので LCD は更新しない
        edges = send_pulse(tx, sym, boundary)
        display.update(now, "TX")  # 信号の立ち下がり後に書く(送信タイミングを乱さない)
        publish(boundary, idx, sym, edges)
        if idx == 59 and len(frame) == 61:  # うるう秒の挿入: 60 秒目を単調時計で送る
            start = mono0 + S
            sleep_until(start, time.monotonic_ns)
            publish(boundary + S, 60, frame[60], send_pulse(tx, frame[60], start, time.monotonic_ns))
            if time.time_ns() >= boundary + S:
                log.warning("system clock did not repeat the leap second; chrony leapsecmode?")


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
    callsign = cfg.get("callsign", {}).get("enabled", False)  # 既定は送らない(README「呼出符号」参照)
    status_cfg = cfg.get("status", {})
    status = StatusWriter(status_cfg.get("path", STATUS_PATH)) if status_cfg.get("enabled", True) else None
    leap_cfg = cfg.get("leap", {})
    leap = LeapSchedule(path=leap_cfg.get("file", DEFAULT_PATH)) if leap_cfg.get("enabled", True) else None

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
        run(tx, monitor, stop, Display(lcd, khz), leap, callsign, status, khz)
    finally:
        if lcd is not None:
            lcd.close()
        tx.close()


if __name__ == "__main__":
    main()
