import argparse
import logging
import os
import signal
import time
import tomllib
from datetime import datetime

from .encoder import JST, PULSE_WIDTH, encode_minute
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


def run(tx, monitor: SyncMonitor, stop: dict) -> None:
    cur_minute, frame = None, None
    while not stop["flag"]:
        boundary = (time.time_ns() // S + 1) * S
        sleep_until(boundary)
        if time.time_ns() - boundary > MAX_LATE_NS:
            log.warning("missed second boundary, skipping")
            continue

        if monitor.ok != tx.carrier_on:
            tx.set_carrier(monitor.ok)
        if not monitor.ok:
            continue

        minute = boundary // (60 * S)
        if minute != cur_minute:
            t = datetime.fromtimestamp(minute * 60, JST)
            frame, cur_minute = encode_minute(t), minute
            log.info("frame %s JST", t.strftime("%Y-%m-%d %H:%M (%a)"))
        sym = frame[(boundary // S) % 60]
        tx.level(True)
        sleep_until(boundary + int(PULSE_WIDTH[sym] * S))
        tx.level(False)


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
    rtc = cfg.get("rtc", {})

    state_file = None
    if rtc.get("enabled", False):
        if rtc_present() or args.dry_run:
            state_file = rtc.get("state_file", "/var/lib/jjyd/last_sync")
        else:
            log.warning("[rtc] enabled but /sys/class/rtc/rtc0 not found; RTC mode ignored")
    monitor = SyncMonitor(ts.get("check_interval_s", 30), ts.get("holdover_s", 21600),
                          state_file=state_file, rtc_holdover_s=rtc.get("holdover_s", 86400))
    if args.dry_run:
        monitor.checker = lambda: True
        tx = DryRunTransmitter()
    else:
        tx = Transmitter(c.get("khz", 60), c.get("pwm_chip", 0), c.get("pwm_channel", 0), lv.get("gpio", 23),
                         select_gpio=c.get("select_gpio"))
        try:  # 可能ならリアルタイム優先度
            os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(20))
        except (PermissionError, AttributeError, OSError):
            log.warning("SCHED_FIFO unavailable; timing jitter may be larger")

    stop = {"flag": False}
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.update(flag=True))

    monitor.start()
    try:
        run(tx, monitor, stop)
    finally:
        tx.close()


if __name__ == "__main__":
    main()
