"""chrony の同期状態を監視し、送信してよいかを判定する。

RTC(DS3231)を使う設定のときは、最後に同期できた時刻をファイルに残し、再起動直後に
chrony が未同期でも「RTC が正しい時刻を保持している」と判断できる間は送信を許可する。
"""
import logging
import os
import subprocess
import threading
import time

log = logging.getLogger("jjyd.timesync")

PERSIST_INTERVAL_S = 900  # SD カードの書き込みを抑えるため15分に1回


LOCAL_REFID = "7F7F0101"  # chrony の `local` 指令による自己参照(外部の時刻源に同期しているわけではない)
MAX_OFFSET_S = 0.25       # システム時刻が NTP の時刻からこの秒数を超えてずれている間は、同期済みとみなさない


def tracking_ok(line: str, max_offset_s: float = MAX_OFFSET_S) -> bool:
    """`chronyc -c tracking` の 1 行から、送信してよい時刻かを判定する。

    外部の時刻源に同期していて(`local stratum` の自己参照は除く)、システム時刻のずれが小さいこと。
    起動直後は、同期先を選んだ後でもステップ補正が終わるまで時計が数分ずれていることがある。
    """
    # refid,name,stratum,reftime,sysoffset,lastoffset,rms,freq,resid,skew,rootdelay,rootdisp,interval,leap
    f = line.strip().split(",")
    refid, stratum, offset, leap = f[0], int(f[2]), float(f[4]), f[13]
    return refid != LOCAL_REFID and 0 < stratum < 16 and leap != "Not synchronised" and abs(offset) <= max_offset_s


def chrony_synced() -> bool:
    """chronyc tracking が「外部の時刻源に同期済みで、時計が合っている」ことを示していれば True。"""
    out = subprocess.run(
        ["chronyc", "-c", "tracking"], capture_output=True, text=True, timeout=5, check=True
    ).stdout
    return tracking_ok(out)


def rtc_present() -> bool:
    return os.path.exists("/sys/class/rtc/rtc0")


class SyncMonitor(threading.Thread):
    """`ok` は「最後に同期を確認してから holdover 秒以内」の間だけ True。

    state_file を指定すると RTC モードになる: 起動時に前回同期時刻を読み、現在のシステム時刻
    (RTC 由来)との差が 0 以上 rtc_holdover_s 以内なら、その分だけ同期済みとして扱う。
    RTC の電池切れ等で時刻が巻き戻っていれば差が負になるので信用しない。
    """

    def __init__(self, check_interval_s: float, holdover_s: float, checker=chrony_synced,
                 state_file: str | None = None, rtc_holdover_s: float = 86400,
                 wall=time.time, mono=time.monotonic):
        super().__init__(daemon=True, name="sync-monitor")
        self.interval = check_interval_s
        self.holdover = holdover_s
        self.limit = holdover_s
        self.checker = checker
        self.state_file = state_file
        self.rtc_holdover = rtc_holdover_s
        self.wall, self.mono = wall, mono
        self.last_ok: float | None = None
        self.last_persist = 0.0
        self.ok = False
        if state_file:
            self._restore()

    def _restore(self) -> None:
        try:
            with open(self.state_file) as f:
                last_sync = float(f.read().strip())
        except (OSError, ValueError):
            log.info("no previous sync record; waiting for NTP")
            return
        age = self.wall() - last_sync
        if 0 <= age <= self.rtc_holdover:
            self.last_ok = self.mono() - age
            self.limit = self.rtc_holdover
            log.info("restored from RTC: last sync %.0f s ago", age)
        else:
            log.warning("RTC time not trusted (age %.0f s); waiting for NTP", age)

    def _persist(self) -> None:
        if not self.state_file or self.mono() - self.last_persist < PERSIST_INTERVAL_S:
            return
        try:
            tmp = self.state_file + ".tmp"
            with open(tmp, "w") as f:
                f.write(f"{self.wall():.0f}\n")
            os.replace(tmp, self.state_file)
            self.last_persist = self.mono()
        except OSError as e:
            log.warning("cannot write %s: %s", self.state_file, e)

    def evaluate(self, synced: bool) -> bool:
        """1回分の判定。テストしやすいように run() から分離。"""
        if synced:
            self.last_ok = self.mono()
            self.limit = self.holdover
            self._persist()
        return self.last_ok is not None and self.mono() - self.last_ok <= self.limit

    def run(self) -> None:
        while True:
            try:
                synced = self.checker()
            except Exception as e:  # chronyc 不在・タイムアウト等
                log.warning("sync check failed: %s", e)
                synced = False
            ok = self.evaluate(synced)
            if ok != self.ok:
                log.info("time source %s", "OK -> transmit" if ok else "LOST -> carrier muted")
            self.ok = ok
            time.sleep(self.interval)
