"""うるう秒の予定(leap-seconds.list)を読み、JJY のうるう秒情報(LS1/LS2)と最終分の扱いを決める。

JJY のうるう秒は日本時間で実施月の1日9時(= UTC 0時)の直前に行う。
- 予告 LS1/LS2: 実施前月の2日 9:00 JST から、実施月の1日 8:59 JST の分まで送る。
- 実施する分(1日 8:59 JST): 正(挿入)なら 61 秒(59 秒は "0"、P0 は 60 秒)、負(削除)なら 59 秒(P0 は 58 秒)。

leap-seconds.list は NTP 形式(tzdata が /usr/share/zoneinfo/leap-seconds.list に置く)。
各行は「NTP 秒 TAI-UTC」で、その時刻から TAI-UTC が変わる。差分が +1 なら挿入、-1 なら削除。
"""
import logging
import os
from datetime import datetime, timedelta, timezone

from .encoder import JST

log = logging.getLogger("jjyd.leap")

DEFAULT_PATH = "/usr/share/zoneinfo/leap-seconds.list"
NTP_EPOCH = datetime(1900, 1, 1, tzinfo=timezone.utc)


def parse_leap_seconds_list(text: str) -> tuple[list[tuple[datetime, int]], datetime | None]:
    """[(うるう秒の直後の UTC 時刻, +1/-1), ...] と、リストの有効期限(あれば)を返す。"""
    table: list[tuple[datetime, int]] = []
    expiry = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#@"):
            expiry = NTP_EPOCH + timedelta(seconds=int(line[2:].split()[0]))
            continue
        if not line or line.startswith("#"):
            continue
        ntp, tai_utc = line.split("#")[0].split()[:2]
        table.append((NTP_EPOCH + timedelta(seconds=int(ntp)), int(tai_utc)))
    table.sort()
    events = []
    for (_, prev), (when, cur) in zip(table, table[1:]):
        if cur != prev:
            events.append((when, 1 if cur > prev else -1))
    return events, expiry


class LeapSchedule:
    def __init__(self, events: list[tuple[datetime, int]] | None = None, path: str | None = None):
        self.events = sorted(events or [])
        self.path = path
        self.mtime = None
        if path:
            self.reload_if_changed()

    def reload_if_changed(self) -> None:
        """ファイルが更新されていれば読み直す(読めなければ直前の内容を使い続ける)。"""
        if not self.path:
            return
        try:
            mtime = os.stat(self.path).st_mtime
            if mtime == self.mtime:
                return
            with open(self.path, encoding="ascii", errors="replace") as f:
                events, expiry = parse_leap_seconds_list(f.read())
        except (OSError, ValueError) as e:
            if self.mtime is None:
                log.info("leap second list not available (%s): %s", self.path, e)
                self.mtime = -1  # 同じ警告を繰り返さない
            return
        self.events, self.mtime = events, mtime
        log.info("leap second list loaded: %d events, last=%s", len(events),
                 events[-1][0].date() if events else "-")
        if expiry and expiry < datetime.now(timezone.utc):
            log.warning("leap second list expired on %s; update tzdata", expiry.date())

    def lookup(self, minute_start: datetime) -> tuple[int, bool]:
        """(うるう秒予告 0/+1/-1, この分が実施される最終分か) を返す。minute_start は分の先頭時刻。"""
        t = minute_start.astimezone(JST)
        for when, sign in self.events:
            end = when.astimezone(JST)
            y, m = (end.year, end.month - 1) if end.month > 1 else (end.year - 1, 12)
            warn_start = datetime(y, m, 2, 9, 0, tzinfo=JST)
            if warn_start <= t < end:
                return sign, t + timedelta(minutes=1) == end
        return 0, False
