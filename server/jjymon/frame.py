"""JJY フレームの各秒が何を表すか(分・時・通算日・年・曜日・パリティ・うるう秒予告など)と、フレームの読み取り。

配置は jjyd.encoder.encode_minute と同じ。毎時 15・45 分の呼出符号フレームでは、40〜48 秒が呼出符号、50〜55 秒が停波予告 ST1〜ST6 になる。
"""
# (項目, 開始秒, 各ビットの重み)。値は、'1' のビットの重みの合計
SPEC = (
    ("min", 1, (40, 20, 10)), ("min", 5, (8, 4, 2, 1)),
    ("hour", 12, (20, 10)), ("hour", 15, (8, 4, 2, 1)),
    ("doy", 22, (200, 100)), ("doy", 25, (80, 40, 20, 10)), ("doy", 30, (8, 4, 2, 1)),
    ("year", 41, (80, 40, 20, 10)), ("year", 45, (8, 4, 2, 1)),
    ("wday", 50, (4, 2, 1)),
)
MARKERS = {0: "M", 9: "P1", 19: "P2", 29: "P3", 39: "P4", 49: "P5", 59: "P0"}
SINGLE = {36: ("par", "PA1"), 37: ("par", "PA2"), 38: ("su", "SU1"), 40: ("su", "SU2"), 53: ("ls", "LS1"), 54: ("ls", "LS2")}

# 表の行: (項目, 名前, 秒の範囲)。色は項目ごと
ROWS = (
    ("min", "分", "1–8 秒"), ("hour", "時", "12–18 秒"), ("doy", "通算日", "22–33 秒"),
    ("year", "年(下 2 桁)", "41–48 秒"), ("wday", "曜日", "50–52 秒"),
    ("par", "パリティ PA1・PA2", "36・37 秒"), ("su", "夏時間 SU1・SU2", "38・40 秒"),
    ("ls", "うるう秒予告 LS1・LS2", "53・54 秒"), ("res", "予備(常に 0)", ""),
    ("mk", "マーカー M・P1〜P5・P0", "0・9・19… 秒"), ("call", "呼出符号(15・45 分のみ)", "40–48 秒"),
    ("st", "停波予告 ST1〜ST6(同上)", "50–55 秒"),
)
COLOR = {"min": "#4ec9b0", "hour": "#6aa5ff", "doy": "#c792ea", "year": "#ffb454", "wday": "#7fdc7f", "par": "#ff7a90",
         "su": "#a8b3bd", "ls": "#ffd23f", "res": "#4a5a69", "mk": "#f0a030", "call": "#d070e0", "st": "#b8b8ff"}


def is_callsign(frame: str | None) -> bool:
    return bool(frame) and len(frame) > 40 and frame[40] == "C"


def layout(callsign: bool = False) -> dict[int, tuple[str, str]]:
    """秒 -> (項目, ビットの意味の短い表示)。"""
    out: dict[int, tuple[str, str]] = {s: ("res", "") for s in range(61)}
    for field, start, weights in SPEC:
        for i, w in enumerate(weights):
            out[start + i] = (field, str(w))
    for s, v in SINGLE.items():
        out[s] = v
    for s, name in MARKERS.items():
        out[s] = ("mk", name)
    if callsign:
        for s in range(40, 49):
            out[s] = ("call", "JJY")
        for i in range(6):
            out[50 + i] = ("st", f"ST{i + 1}")
    return out


def decode(frame: str) -> dict:
    """フレームを読む。送らない項目は None。"""
    if not frame or len(frame) < 59:
        return {}
    bit = lambda s: 1 if frame[s] == "1" else 0  # noqa: E731
    val: dict = {k: 0 for k in ("min", "hour", "doy", "year", "wday")}
    for field, start, weights in SPEC:
        if field in ("year", "wday") and is_callsign(frame):
            continue
        val[field] += sum(w * bit(start + i) for i, w in enumerate(weights))
    call = is_callsign(frame)
    if call:
        val["year"] = val["wday"] = None
    else:
        val["year"] += 2000
    val["pa1_ok"] = bit(36) == sum(bit(s) for s in range(12, 19)) % 2
    val["pa2_ok"] = bit(37) == sum(bit(s) for s in range(1, 9)) % 2
    val["su"] = (bit(38), 0 if call else bit(40))
    val["ls"] = None if call else (bit(53), bit(54))  # (1, 1) = 挿入予告、(1, 0) = 削除予告
    val["st"] = tuple(bit(50 + i) for i in range(6)) if call else None
    return val
