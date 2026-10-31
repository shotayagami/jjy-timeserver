"""jjyd が今この瞬間に出している信号(搬送波の振幅と基板の LED)を、フレームと時刻から再現する。

jjyd は秒ごとの送信が終わった後に状態を書く(送信のタイミングを乱さないため)ので、モニタは
「その分のフレーム」と「今の時刻」から、送信中の信号を計算する。規則は jjyd.main の send_pulse / send_callsign_second と同じ。
"""
from dataclasses import dataclass

from jjyd.encoder import CALLSIGN_START, PULSE_WIDTH, callsign_keying

_KEYING = callsign_keying()


@dataclass
class Signal:
    idx: int | None            # フレーム内の秒(0〜59)。不明なら None
    sym: str | None            # 'M' / '1' / '0' / 'C'。不明なら None
    amplitude: float           # 搬送波の振幅(0 = 停波、0.1 = 低レベル、1 = 最大)
    d1: bool                   # 赤 LED: 高レベル(最大振幅)の間だけ点灯
    d2: bool                   # 黄緑 LED: 低レベルの間(次の秒頭まで)点灯
    d3: bool = True            # 黄 LED: 通電表示(常時点灯)


def at(frame: str | None, now: float, carrier: bool) -> Signal:
    """now(UNIX 秒)の信号。frame はその分の 60 シンボル(MARKER/1/0/C)で、無ければ None。"""
    sec = int(now // 1)
    phase = now - sec
    idx = sec % 60
    sym = frame[idx] if frame and idx < len(frame) else ("M" if idx == 0 else None)
    if not carrier or sym is None:
        return Signal(idx, sym, 0.0, False, False)
    if sym == "C":  # 呼出符号: 搬送波を 0%/100% でキーイング。最大振幅のまま、キーオン中は D2 が消える
        k = idx - CALLSIGN_START + phase
        on = any(a <= k < b for a, b in _KEYING)
        return Signal(idx, sym, 1.0 if on else 0.0, True, not on)
    high = phase < PULSE_WIDTH[sym]
    return Signal(idx, sym, 1.0 if high else 0.1, high, not high)
