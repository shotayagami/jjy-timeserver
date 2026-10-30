"""JJY (日本標準時 標準電波) タイムコードのエンコーダ。

1フレーム = 1分 = 60シンボル。各シンボルは 'M'(マーカー) / '1' / '0'。
各秒の先頭で振幅を最大にし、シンボルごとの幅だけ保持してから 10% に落とす。
"""
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

# 各シンボルでキャリアが最大振幅を保つ時間 [秒]
PULSE_WIDTH = {"M": 0.2, "1": 0.5, "0": 0.8}

MARKER_SECONDS = (0, 9, 19, 29, 39, 49, 59)

# 送信信号 LED: 高レベルが終わってから次の秒頭まで(= 低レベル期間)だけ点灯する。
# ビット1 = 0.5 秒点灯、ビット0 = 0.2 秒点灯して消灯、マーカー = 0.8 秒点灯。
LED_ON_SECONDS = {sym: round(1.0 - w, 3) for sym, w in PULSE_WIDTH.items()}


def _bits(value: int, width: int) -> list[int]:
    return [(value >> i) & 1 for i in range(width - 1, -1, -1)]


def encode_minute(dt: datetime) -> list[str]:
    """dt が属する分の JJY フレーム(60要素)を返す。秒以下は無視する。"""
    dt = dt.astimezone(JST)
    sec = [0] * 60

    def put(start: int, bits: list[int]) -> None:
        sec[start:start + len(bits)] = bits

    minute, hour = dt.minute, dt.hour
    yday = dt.timetuple().tm_yday
    year = dt.year % 100
    wday = (dt.weekday() + 1) % 7  # 日曜=0

    put(1, _bits(minute // 10, 3))
    put(5, _bits(minute % 10, 4))
    put(12, _bits(hour // 10, 2))
    put(15, _bits(hour % 10, 4))
    put(22, _bits(yday // 100, 2))
    put(25, _bits(yday // 10 % 10, 4))
    put(30, _bits(yday % 10, 4))
    put(41, _bits(year // 10, 4))
    put(45, _bits(year % 10, 4))
    put(50, _bits(wday, 3))

    sec[36] = sum(sec[12:19]) % 2  # PA1: 時の偶数パリティ
    sec[37] = sum(sec[1:9]) % 2    # PA2: 分の偶数パリティ
    # 38 SU1 / 40 SU2 (夏時間) と 53,54 (うるう秒予告) は常に0

    symbols = [str(b) for b in sec]
    for m in MARKER_SECONDS:
        symbols[m] = "M"
    return symbols
