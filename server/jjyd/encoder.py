"""JJY (日本標準時 標準電波) タイムコードのエンコーダ。

1フレーム = 1分 = 60シンボル。各シンボルは 'M'(マーカー) / '1' / '0'。
各秒の先頭で振幅を最大にし、シンボルごとの幅だけ保持してから 10% に落とす。
毎時15分・45分のフレームだけは 40〜48 秒に呼出符号(モールス 'JJY')を入れる。
この区間のシンボルは 'C' で、搬送波を 0%/100% でキーイングする(intervals は callsign_keying)。
"""
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

# 各シンボルでキャリアが最大振幅を保つ時間 [秒]
PULSE_WIDTH = {"M": 0.2, "1": 0.5, "0": 0.8}

MARKER_SECONDS = (0, 9, 19, 29, 39, 49, 59)

# 呼出符号送出時のフレーム(毎時15分・45分)。40〜48 秒が呼出符号、50〜55 秒が停波予告 ST1〜ST6。
# NICT の現行図(nict.go.jp/en/sts/jjy_signal.html の "when minute is 15 or 45")と同じ配置:
# 年・曜日・LS は送らず、40〜48 秒=呼出符号、49 秒=P5、50〜55 秒=ST1〜ST6、56〜58 秒=0、59 秒=P0。
CALLSIGN_MINUTES = (15, 45)
CALLSIGN_START, CALLSIGN_END = 40, 49  # [40, 49) 秒
ST_NONE = (0, 0, 0, 0, 0, 0)  # 停波予定なし
# 実測(seppina.cocolog-nifty.com 2016-01 "JJYのコールサイン")に合わせる: 40.0〜49.0 秒の 9 秒間 = 111 単位
# = 前の余白 7 + JJY(45) + 語間 7 + JJY(45) + 後の余白 7。1 単位 ≒ 81.1 ms(約 15 wpm)。
MORSE_UNIT = 9.0 / 111
_MORSE = {"J": ".---", "Y": "-.--"}

# 送信信号 LED: 高レベルが終わってから次の秒頭まで(= 低レベル期間)だけ点灯する。
# ビット1 = 0.5 秒点灯、ビット0 = 0.2 秒点灯して消灯、マーカー = 0.8 秒点灯。
LED_ON_SECONDS = {sym: round(1.0 - w, 3) for sym, w in PULSE_WIDTH.items()}


def _bits(value: int, width: int) -> list[int]:
    return [(value >> i) & 1 for i in range(width - 1, -1, -1)]


def callsign_keying(text: str = "JJY", repeat: int = 2, unit: float = MORSE_UNIT) -> list[tuple[float, float]]:
    """呼出符号の搬送波 ON 区間 [(開始, 終了), ...] を、40 秒を 0 とした秒数で返す。

    ドット=1 単位、ダッシュ=3 単位、符号内の間隔=1 単位、文字間=3 単位、語間(繰り返しの間)=7 単位。
    最初の符号の前にも 7 単位の余白があり、最後の符号の後ろの 7 単位が 49 秒(P5)まで続く。
    """
    out, t = [], 7 * unit
    for r in range(repeat):
        if r:
            t += 7 * unit
        for ci, ch in enumerate(text):
            if ci:
                t += 3 * unit
            for ei, el in enumerate(_MORSE[ch]):
                if ei:
                    t += unit
                d = (1 if el == "." else 3) * unit
                out.append((round(t, 6), round(t + d, 6)))
                t += d
    return out


def encode_minute(dt: datetime, leap: int = 0, leap_now: bool = False, callsign: bool = False) -> list[str]:
    """dt が属する分の JJY フレーム(通常 60要素)を返す。秒以下は無視する。

    leap: うるう秒予告(+1=挿入, -1=削除, 0=なし)。LS1/LS2 に反映する。
    leap_now: この分の終わりにうるう秒を実施する(= 1日 8:59 JST の分)。
      挿入なら 61 要素(59 秒は '0'、P0 は 60 秒)、削除なら 59 要素(P0 は 58 秒)を返す。
    callsign: True のとき、毎時15・45分だけ呼出符号送出時のフレームにする(既定は False)。
      "JJY" は NICT の局の呼出符号かつ登録商標なので、明示的に有効にしない限り送らない。
      False なら15・45分も通常フレーム(年・曜日・LS入り)で、電波時計からはそのまま使える。
    """
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
    callsign = callsign and minute in CALLSIGN_MINUTES
    if callsign:
        put(50, list(ST_NONE))  # 曜日・うるう秒情報の代わりに停波予告 ST1〜ST6
    else:
        put(50, _bits(wday, 3))

    sec[36] = sum(sec[12:19]) % 2  # PA1: 時の偶数パリティ
    sec[37] = sum(sec[1:9]) % 2    # PA2: 分の偶数パリティ
    # 38 SU1 / 40 SU2 (夏時間) は常に0
    if leap and not callsign:  # 15/45 分は 53,54 秒が ST4,ST5
        sec[53] = 1               # LS1
        sec[54] = int(leap > 0)   # LS2: 11=挿入, 10=削除

    symbols = [str(b) for b in sec]
    if callsign:
        symbols[CALLSIGN_START:CALLSIGN_END] = ["C"] * (CALLSIGN_END - CALLSIGN_START)
    for m in MARKER_SECONDS:
        symbols[m] = "M"
    if leap_now and leap > 0:
        symbols[59] = "0"
        symbols.append("M")
    elif leap_now and leap < 0:
        symbols[58] = "M"
        del symbols[59]
    return symbols
