"""jjyd が今この瞬間に出している信号(搬送波の振幅と基板の LED)を、フレームと時刻から再現する。

jjyd は秒ごとの送信が終わった後に状態を書く(送信のタイミングを乱さないため)ので、モニタは
「その分のフレーム」と「今の時刻」から、送信中の信号を計算する。規則は jjyd.main の send_pulse / send_callsign_second と同じ。
"""
from dataclasses import dataclass
from datetime import datetime

from jjyd.encoder import CALLSIGN_START, JST, PULSE_WIDTH, callsign_keying
from jjyd.lcd import format_lines

_KEYING = callsign_keying()


@dataclass
class Signal:
    idx: int | None            # フレーム内の秒(0〜59)。不明なら None
    sym: str | None            # 'M' / '1' / '0' / 'C'。不明なら None
    amplitude: float           # 搬送波の振幅(0 = 停波、0.1 = 低レベル、1 = 最大)
    d1: bool                   # 赤 LED: 高レベル(最大振幅)の間だけ点灯
    d2: bool                   # 黄緑 LED: 低レベルの間(次の秒頭まで)点灯
    d3: bool = True            # 黄 LED: 通電表示(常時点灯)


def _state(sym: str | None, idx: int, phase: float, carrier: bool) -> tuple[float, bool, bool]:
    """秒の頭から phase 秒後の (振幅, D1, D2)。"""
    if not carrier or sym is None:
        return 0.0, False, False
    if sym == "C":  # 呼出符号: 搬送波を 0%/100% でキーイング。最大振幅のまま、キーオン中は D2 が消える
        k = idx - CALLSIGN_START + phase
        on = any(a <= k < b for a, b in _KEYING)
        return (1.0 if on else 0.0), True, not on
    high = phase < PULSE_WIDTH[sym]
    return (1.0 if high else 0.1), high, not high


def at(frame: str | None, now: float, carrier: bool) -> Signal:
    """now(UNIX 秒)の信号。frame はその分の 60 シンボル(MARKER/1/0/C)で、無ければ None。"""
    sec = int(now // 1)
    idx = sec % 60
    sym = frame[idx] if frame and idx < len(frame) else ("M" if idx == 0 else None)
    amp, d1, d2 = _state(sym, idx, now - sec, carrier)
    return Signal(idx, sym, amp, d1, d2)


def segments(sym: str | None, idx: int, carrier: bool) -> list[tuple[float, float, bool, bool]]:
    """1 秒の間の信号の変化を [(秒の頭からの時刻, 振幅, D1, D2), ...] で返す(次の変化まで、その値が続く)。波形を正確な位置で描くのに使う。"""
    cuts = [0.0]
    if carrier and sym == "C":
        k0 = idx - CALLSIGN_START
        cuts += sorted({x for a, b in _KEYING for x in (a - k0, b - k0) if 0 < x < 1})
    elif carrier and sym is not None:
        cuts.append(PULSE_WIDTH[sym])
    return [(c, *_state(sym, idx, c + 1e-9, carrier)) for c in cuts]


def lcd_lines(frame: str | None, now: float, carrier: bool, khz: int) -> tuple[str, str]:
    """基板の LCD(16x2)に今出ている 2 行。jjyd.main の Display.update と同じ規則で、同じ format_lines で作る。

    送信中は、各秒の高レベルが終わった後(立ち下がり後)にその秒の時刻へ更新する。呼出符号の秒(40〜48 秒)は更新しない。
    停止中は、各秒の頭で「OFF」の表示に更新する。
    """
    sec = int(now // 1)
    if not carrier:
        return format_lines(datetime.fromtimestamp(sec, JST), khz, "OFF")

    def sym_of(s: int) -> str | None:
        return frame[s % 60] if frame and s % 60 < len(frame) else ("M" if s % 60 == 0 else None)

    u = sec if now - sec >= PULSE_WIDTH.get(sym_of(sec) or "", 1.0) else sec - 1  # 今の秒は、立ち下がり後に更新される
    for _ in range(10):  # 呼出符号の秒はさかのぼる(その秒は更新されない)
        if sym_of(u) != "C":
            break
        u -= 1
    return format_lines(datetime.fromtimestamp(u, JST), khz, "TX")
