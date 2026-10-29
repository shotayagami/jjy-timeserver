"""JJY HAT (40kHz / 60kHz ソフト切替, RTC 搭載) の KiCad プロジェクトを生成する。

    python gen_kicad.py        # jjy-hat.kicad_pro / .kicad_sch / .kicad_pcb を出力し、配線チェックを実行

部品・ネット・配置・配線をこのファイルで定義しているので、変更はここを直して再生成する。
"""
import json
import math
import sys
import uuid
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I でも同じ場所の kicad_lib を読めるように
import kicad_lib as KL  # noqa: E402

OUT = Path(__file__).resolve().parent
PROJ = "jjy-hat"
NS = uuid.UUID("6f1f4a52-3c5d-4b8e-9d0a-0a5e17c0de01")


def U(name: str) -> str:
    return str(uuid.uuid5(NS, name))


ROOT_UUID = U("root-sheet")

# ---------------------------------------------------------------- 部品定義
NETS = ["", "GND", "+3V3", "/CARRIER", "/LEVEL", "/NA", "/NB", "/DRV", "/ANT", "/LED_A", "/I2C_SDA", "/I2C_SCL", "/VBAT", "/CSW", "/RLY_A", "/FSEL"]
NID = {n: i for i, n in enumerate(NETS)}
SCH_NAME = {n: n.lstrip("/") for n in NETS}  # 回路図上のラベル名

GND_PINS = (6, 9, 14, 20, 25, 30, 34, 39)
J1_NET = {p: "GND" for p in GND_PINS}
J1_NET.update({1: "+3V3", 3: "/I2C_SDA", 5: "/I2C_SCL", 37: "/FSEL", 12: "/CARRIER", 16: "/LEVEL", 17: "+3V3"})
J1_NC = [p for p in range(1, 41) if p not in J1_NET]

U1_NET = {1: "GND", 2: "/CARRIER", 3: "/NA", 4: "/LEVEL", 5: "/CARRIER", 6: "/NB", 7: "GND",
          8: "", 9: "GND", 10: "+3V3", 11: "", 12: "GND", 13: "+3V3", 14: "+3V3"}

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
LED0603 = "LED_SMD:LED_0603_1608Metric"
SOIC14 = "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm"
HDR40 = "Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical"
HDR2 = "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"
SO4 = "Package_SO:SO-4_4.4x4.3mm_P2.54mm"
SOIC16W = "Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm"
BATT = "Battery:BatteryHolder_MYOUNG_BS-07-A1BJ001_CR2032"
MH = "MountingHole:MountingHole_2.7mm_M2.5"

# ref, value, sch lib, footprint, sch (x,y), pcb (x,y,angle), {pin: net}
PARTS = [
    ("J1", "GPIO 2x20 stacking header", "Connector_Generic:Conn_02x20_Odd_Even", HDR40, (63.5, 152.4), (8.37, 4.77, 90), J1_NET),
    ("U1", "74LVC125", "JJY:74LVC125", SOIC14, (203.2, 127), (40, 24, 0), U1_NET),
    ("R1", "1k", "Device:R", R0603, (127, 76.2), (32, 22.73, 0), {1: "/DRV", 2: "/NA"}),
    ("R2", "100", "Device:R", R0603, (152.4, 76.2), (32, 26.54, 0), {1: "/DRV", 2: "/NB"}),
    ("R3", "10k", "Device:R", R0603, (254, 76.2), (31.5, 7.4, 0), {1: "+3V3", 2: "/LEVEL"}),
    ("R4", "10k", "Device:R", R0603, (279.4, 76.2), (19.5, 8.5, 0), {1: "GND", 2: "/CARRIER"}),
    ("R5", "1k", "Device:R", R0603, (304.8, 76.2), (37.5, 7.4, 0), {1: "+3V3", 2: "/LED_A"}),
    ("D1", "LED red", "Device:LED", LED0603, (330.2, 76.2), (41.0, 7.4, 180), {1: "/LEVEL", 2: "/LED_A"}),
    ("C1", "100n", "Device:C", C0603, (254, 127), (48.5, 22, 0), {1: "+3V3", 2: "GND"}),
    ("C2", "4.7n C0G", "Device:C", C0603, (127, 177.8), (30, 33, 0), {1: "/DRV", 2: "/ANT"}),
    ("C3", "2.2n C0G", "Device:C", C0603, (152.4, 177.8), (30, 36, 0), {1: "/DRV", 2: "/ANT"}),
    ("C4", "150p C0G", "Device:C", C0603, (177.8, 177.8), (30, 39, 0), {1: "/DRV", 2: "/ANT"}),
    ("C5", "trim (DNP)", "Device:C", C0603, (203.2, 177.8), (30, 42, 0), {1: "/DRV", 2: "/ANT"}),
    ("J2", "Antenna", "Connector_Generic:Conn_01x02", HDR2, (254, 177.8), (50, 38, 0), {1: "/ANT", 2: "GND"}),
    # RTC: DS3231SN + 電池ホルダ(CR2032, 手はんだ)。SDA/SCL は Pi 側の 1.8k プルアップを使う。
    ("U2", "DS3231SN#", "JJY:DS3231SN", SOIC16W, (330.2, 127), (20, 22, 180),
     {2: "+3V3", 13: "GND", 14: "/VBAT", 15: "/I2C_SDA", 16: "/I2C_SCL"}),
    ("C6", "100n", "Device:C", C0603, (355.6, 127), (26.4, 29.6, 90), {1: "GND", 2: "+3V3"}),
    # 40/60kHz 切替: GPIO26=High でフォトモスリレー K1 が C7〜C9 (9.1nF) を共振回路に追加 -> 40kHz
    ("C7", "4.7n C0G", "Device:C", C0603, (127, 228.6), (30, 45, 0), {1: "/CSW", 2: "/ANT"}),
    ("C8", "2.2n C0G", "Device:C", C0603, (152.4, 228.6), (30, 47.5, 0), {1: "/CSW", 2: "/ANT"}),
    ("C9", "2.2n C0G", "Device:C", C0603, (177.8, 228.6), (30, 50, 0), {1: "/CSW", 2: "/ANT"}),
    ("K1", "AQY212SX", "JJY:AQY212S", SO4, (203.2, 228.6), (38, 50.9, 180), {1: "/RLY_A", 2: "GND", 3: "/DRV", 4: "/CSW"}),
    ("R6", "330", "Device:R", R0603, (254, 228.6), (47, 52.17, 0), {1: "/RLY_A", 2: "/FSEL"}),
    ("BT1", "CR2032 holder", "Device:Battery_Cell", BATT, (381, 127), (16, 30.9, 270), {1: "/VBAT", 2: "GND"}),
    # 取り付け穴(HAT 規格: 65x56mm の四隅から 3.5mm)
    ("H1", "MountingHole", "Mechanical:MountingHole", MH, (330.2, 254), (3.5, 3.5, 0), {}),
    ("H2", "MountingHole", "Mechanical:MountingHole", MH, (342.9, 254), (61.5, 3.5, 0), {}),
    ("H3", "MountingHole", "Mechanical:MountingHole", MH, (355.6, 254), (3.5, 52.5, 0), {}),
    ("H4", "MountingHole", "Mechanical:MountingHole", MH, (368.3, 254), (61.5, 52.5, 0), {}),
]
BOARD_W, BOARD_H = 65.0, 56.0

# ---------------------------------------------------------------- PCB 配線
W_SIG, W_PWR = 0.25, 0.3
VIA_D, VIA_DRILL = 0.8, 0.4


def poly(net, layer, w, *pts):
    return [(net, layer, w, pts[i], pts[i + 1]) for i in range(len(pts) - 1)]


TRACKS = []
# CARRIER: GPIO18 -> U1 pin2 (F.Cu) / pin5 (B.Cu 経由)
TRACKS += poly("/CARRIER", "F.Cu", W_SIG, (21.07, 2.23), (22.34, 2.23), (22.34, 11), (35, 11), (35, 21.46), (37.525, 21.46))
TRACKS += poly("/CARRIER", "F.Cu", W_SIG, (37.525, 25.27), (36.8, 25.27))
TRACKS += poly("/CARRIER", "B.Cu", W_SIG, (36.8, 21.46), (36.8, 25.27))
TRACKS += poly("/CARRIER", "F.Cu", W_SIG, (20.325, 8.5), (22.34, 8.5))              # R4 pad2
# LEVEL: GPIO23 -> B.Cu 幹線 -> U1 pin4 / R3 / D1
TRACKS += poly("/LEVEL", "B.Cu", W_SIG, (26.15, 2.23), (27.42, 2.23), (27.42, 24), (34, 24))
TRACKS += poly("/LEVEL", "F.Cu", W_SIG, (34, 24), (37.525, 24))
TRACKS += poly("/LEVEL", "B.Cu", W_SIG, (27.42, 7.4), (43.2, 7.4))
TRACKS += poly("/LEVEL", "F.Cu", W_SIG, (32.325, 7.4), (33.6, 7.4))                 # R3 pad2 -> via
TRACKS += poly("/LEVEL", "F.Cu", W_SIG, (41.825, 7.4), (43.2, 7.4))                 # D1 pad1 -> via
# +3V3
TRACKS += poly("+3V3", "F.Cu", W_PWR, (28.69, 4.77), (28.69, 9), (46, 9), (46, 25.27))
TRACKS += poly("+3V3", "F.Cu", W_PWR, (30.675, 7.4), (28.69, 7.4))                  # R3 pad1
TRACKS += poly("+3V3", "F.Cu", W_PWR, (36.675, 7.4), (36.675, 9))                   # R5 pad1
TRACKS += poly("+3V3", "F.Cu", W_PWR, (42.475, 20.19), (46, 20.19))                 # U1 pin14
TRACKS += poly("+3V3", "F.Cu", W_PWR, (42.475, 21.46), (46, 21.46))                 # U1 pin13
TRACKS += poly("+3V3", "F.Cu", W_PWR, (42.475, 25.27), (46, 25.27))                 # U1 pin10
TRACKS += poly("+3V3", "F.Cu", W_PWR, (46, 22), (47.675, 22))                       # C1 pad1
# NA / NB / LED_A
TRACKS += poly("/NA", "F.Cu", W_SIG, (37.525, 22.73), (32.825, 22.73))
TRACKS += poly("/NB", "F.Cu", W_SIG, (37.525, 26.54), (32.825, 26.54))
TRACKS += poly("/LED_A", "F.Cu", W_SIG, (38.325, 7.4), (40.175, 7.4))
# DRV: R1/R2 -> C2..C5
TRACKS += poly("/DRV", "F.Cu", W_SIG, (31.175, 22.73), (30.2, 22.73), (30.2, 31), (28.5, 31), (28.5, 42))
TRACKS += poly("/DRV", "F.Cu", W_SIG, (31.175, 26.54), (30.2, 26.54))
for y in (33, 36, 39, 42):
    TRACKS += poly("/DRV", "F.Cu", W_SIG, (28.5, y), (29.175, y))
# ANT: C2..C5 -> J2.1
for y in (33, 36, 39, 42):
    TRACKS += poly("/ANT", "F.Cu", W_SIG, (30.825, y), (32.5, y))
TRACKS += poly("/ANT", "F.Cu", W_SIG, (32.5, 33), (32.5, 50))
TRACKS += poly("/ANT", "F.Cu", W_SIG, (32.5, 36), (50, 36), (50, 38))
# RTC (U2): I2C は F.Cu。SCL は SDA の配線をまたぐため B.Cu へ一度くぐる。3.3V は B.Cu で CARRIER の下をくぐる。
TRACKS += poly("/I2C_SDA", "F.Cu", W_SIG, (10.91, 4.77), (10.91, 25.175), (15.35, 25.175))
TRACKS += poly("/I2C_SCL", "F.Cu", W_SIG, (13.45, 4.77), (13.45, 24.0))
TRACKS += poly("/I2C_SCL", "B.Cu", W_SIG, (13.45, 24.0), (13.45, 26.445))
TRACKS += poly("/I2C_SCL", "F.Cu", W_SIG, (13.45, 26.445), (15.35, 26.445))
TRACKS += poly("+3V3", "F.Cu", W_PWR, (28.69, 9), (24, 9))
TRACKS += poly("+3V3", "B.Cu", W_PWR, (24, 9), (24, 10.5), (8.37, 10.5), (8.37, 4.77))
TRACKS += poly("+3V3", "B.Cu", W_PWR, (24, 10.5), (26.4, 10.5), (26.4, 25.175))   # U2 VCC へ
TRACKS += poly("+3V3", "F.Cu", W_PWR, (24.65, 25.175), (26.4, 25.175), (26.4, 28.775))  # U2 pin2 -> C6
TRACKS += poly("/VBAT", "F.Cu", W_SIG, (15.35, 23.905), (17.4, 23.905), (17.4, 27.5), (16, 27.5), (16, 30.9))
TRACKS += poly("GND", "F.Cu", W_SIG, (15.35, 22.635), (17.4, 22.635))       # U2 pin13 -> via
TRACKS += poly("GND", "F.Cu", W_SIG, (26.4, 30.425), (26.4, 32.0))          # C6 -> via
# 40kHz 切替バンク: DRV -[K1]- CSW -[C7..C9]- ANT。K1 の LED は GPIO26 -> R6 -> K1.1
for y in (45, 47.5, 50):
    TRACKS += poly("/ANT", "F.Cu", W_SIG, (30.825, y), (32.5, y))
    TRACKS += poly("/CSW", "F.Cu", W_SIG, (29.175, y), (28.5, y))
TRACKS += poly("/CSW", "F.Cu", W_SIG, (28.5, 45), (28.5, 52.17), (35, 52.17))
TRACKS += poly("/DRV", "F.Cu", W_SIG, (28.5, 42), (28.5, 43.3))
TRACKS += poly("/DRV", "B.Cu", W_SIG, (28.5, 43.3), (33.5, 43.3), (33.5, 49.63))
TRACKS += poly("/DRV", "F.Cu", W_SIG, (33.5, 49.63), (35, 49.63))
TRACKS += poly("/RLY_A", "F.Cu", W_SIG, (41, 52.17), (46.175, 52.17))
TRACKS += poly("/FSEL", "F.Cu", W_SIG, (47.825, 52.17), (54.09, 52.17), (54.09, 4.77))
TRACKS += poly("GND", "F.Cu", W_SIG, (41, 49.63), (42.6, 49.63))
# GND ビア(スタブ + B.Cu のベタへ)
TRACKS += poly("GND", "F.Cu", W_SIG, (37.525, 20.19), (36.4, 20.19))
TRACKS += poly("GND", "F.Cu", W_SIG, (37.525, 27.81), (36.4, 27.81))
TRACKS += poly("GND", "F.Cu", W_SIG, (42.475, 22.73), (44.2, 22.73))
TRACKS += poly("GND", "F.Cu", W_SIG, (42.475, 26.54), (44.2, 26.54))
TRACKS += poly("GND", "F.Cu", W_SIG, (49.325, 22), (50.8, 22))
TRACKS += poly("GND", "F.Cu", W_SIG, (18.675, 8.5), (17.2, 8.5))

VIAS = [("/CARRIER", 36.8, 21.46), ("/CARRIER", 36.8, 25.27),
        ("/LEVEL", 34, 24), ("/LEVEL", 33.6, 7.4), ("/LEVEL", 43.2, 7.4),
        ("GND", 36.4, 20.19), ("GND", 36.4, 27.81), ("GND", 44.2, 22.73), ("GND", 44.2, 26.54),
        ("GND", 50.8, 22), ("GND", 17.2, 8.5), ("+3V3", 24, 9),
        ("/I2C_SCL", 13.45, 24.0), ("/I2C_SCL", 13.45, 26.445), ("+3V3", 26.4, 25.175),
        ("GND", 17.4, 22.635), ("GND", 26.4, 32.0),
        ("/DRV", 28.5, 43.3), ("/DRV", 33.5, 49.63), ("GND", 42.6, 49.63)]


# ---------------------------------------------------------------- 幾何
def rot(x, y, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return x * c + y * s, -x * s + y * c


def fp_pads(footprint):
    """標準ライブラリのパッド情報(dict のリスト)。"""
    return KL.pad_infos(footprint)


def pad_net(ref, fpn, num, nets):
    """パッドのネット名。回路図で未接続のものは KiCad が付ける unconnected-(...) 名。"""
    if not num.isdigit():
        return ""  # 取り付け穴など番号なしのパッド
    return nets.get(int(num), "") or nc_name(ref, fpn, num, nets)


def global_pads():
    """検査用: (ref, pad, net, x, y, w, h, thru, circle)。銅箔を持たない穴は除く。"""
    out = []
    for ref, _v, _s, fpn, _sp, (px, py, ang), nets in PARTS:
        for pd in fp_pads(fpn):
            if pd["type"] == "np_thru_hole":
                continue
            rx, ry = rot(pd["x"], pd["y"], ang)
            w, h = pd["w"], pd["h"]
            if round(pd["angle"] + ang) % 180 == 90:
                w, h = h, w
            circ = pd["shape"] == "circle" or (pd["shape"] == "oval" and abs(w - h) < 1e-9)
            net = nets.get(int(pd["num"]), "") if pd["num"].isdigit() else ""
            out.append((ref, pd["num"], net, px + rx, py + ry, w, h, pd["type"] == "thru_hole", circ))
    return out


def snap_tracks():
    """標準フットプリントのパッド中心とわずかにずれた配線端を、同一ネットのパッド中心へ合わせる。"""
    global TRACKS
    pads = [(n, x, y) for _r, _num, n, x, y, *_ in global_pads() if n]

    def snap(net, pt):
        for n, x, y in pads:
            if n == net and 0 < math.hypot(pt[0] - x, pt[1] - y) <= 0.12:
                return (round(x, 4), round(y, 4))
        return pt
    TRACKS = [(n, l, w, snap(n, a), snap(n, b)) for n, l, w, a, b in TRACKS]


# ---------------------------------------------------------------- チェック
def seg_pt(a, b, p):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def seg_cross(a, b, c, d):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def seg_seg(a, b, c, d):
    if seg_cross(a, b, c, d):
        return 0.0
    return min(seg_pt(a, b, c), seg_pt(a, b, d), seg_pt(c, d, a), seg_pt(c, d, b))


def seg_rect(a, b, cx, cy, w, h):
    x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    inside = lambda p: x0 <= p[0] <= x1 and y0 <= p[1] <= y1
    if inside(a) or inside(b):
        return 0.0
    c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return min(seg_seg(a, b, c[i], c[(i + 1) % 4]) for i in range(4))


def rect_rect(r1, r2):
    dx = max(abs(r1[0] - r2[0]) - (r1[2] + r2[2]) / 2, 0)
    dy = max(abs(r1[1] - r2[1]) - (r1[3] + r2[3]) / 2, 0)
    return math.hypot(dx, dy)


def build_items():
    """検査用の銅箔要素: dict(kind, layers, net, ...)。"""
    items = []
    for net, layer, w, a, b in TRACKS:
        items.append(dict(kind="seg", layers={layer}, net=net, a=a, b=b, r=w / 2, id=f"track {net} {a}->{b} {layer}"))
    for net, x, y in VIAS:
        items.append(dict(kind="seg", layers={"F.Cu", "B.Cu"}, net=net, a=(x, y), b=(x, y), r=VIA_D / 2, via=True, id=f"via {net} ({x},{y})"))
    for ref, num, net, x, y, w, h, thru, circ in global_pads():
        layers = {"F.Cu", "B.Cu"} if thru else {"F.Cu"}
        if circ:
            items.append(dict(kind="seg", layers=layers, net=net, a=(x, y), b=(x, y), r=w / 2, pad=True, id=f"pad {ref}.{num}"))
        else:
            items.append(dict(kind="rect", layers=layers, net=net, c=(x, y), w=w, h=h, pad=True, id=f"pad {ref}.{num}"))
    return items


def dist(i, j):
    if i["kind"] == "seg" and j["kind"] == "seg":
        return seg_seg(i["a"], i["b"], j["a"], j["b"]) - i["r"] - j["r"]
    if i["kind"] == "rect" and j["kind"] == "rect":
        return rect_rect((*i["c"], i["w"], i["h"]), (*j["c"], j["w"], j["h"]))
    s, r = (i, j) if i["kind"] == "seg" else (j, i)
    return seg_rect(s["a"], s["b"], *r["c"], r["w"], r["h"]) - s["r"]


def touches(i, j):
    return dist(i, j) <= 0.0 and bool(i["layers"] & j["layers"])


def check() -> list[str]:
    errs = []
    items = build_items()
    CLR = 0.2
    for i, j in combinations(items, 2):
        if not (i["layers"] & j["layers"]):
            continue
        if i["net"] == j["net"] and i["net"] != "":
            continue
        if i.get("pad") and j.get("pad") and i["net"] == "" and j["net"] == "":
            continue
        d = dist(i, j)
        if d < CLR - 1e-6:
            errs.append(f"clearance {d:.3f} < {CLR}: {i['id']}  vs  {j['id']}")
    # 接続性: GND 以外は銅要素の連結で全パッドが一つに繋がること。GND は F/B ベタ前提で
    # 「スルーホールパッド」か「ビアに接するパッド」であること。
    for net in NETS[2:]:
        its = [x for x in items if x["net"] == net]
        pads = [x for x in its if x.get("pad")]
        parent = list(range(len(its)))

        def find(k):
            while parent[k] != k:
                parent[k] = parent[parent[k]]
                k = parent[k]
            return k
        for a, b in combinations(range(len(its)), 2):
            if touches(its[a], its[b]):
                parent[find(a)] = find(b)
        roots = {find(its.index(p)) for p in pads}
        if len(roots) > 1:
            errs.append(f"net {net}: {len(roots)} disconnected groups")
    for p in [x for x in items if x["net"] == "GND" and x.get("pad")]:
        thru = len(p["layers"]) == 2
        via = any(v.get("via") and v["net"] == "GND" and touches(p, v) for v in items)
        tracked = any(t["net"] == "GND" and not t.get("pad") and not t.get("via") and touches(p, t) for t in items)
        if not (thru or via or tracked):
            errs.append(f"GND pad not tied to plane: {p['id']}")
    for p in [x for x in items if x["net"] == "GND" and not x.get("pad") and not x.get("via")]:
        if not any(v.get("via") and touches(p, v) for v in items if v["net"] == "GND"):
            pass  # スタブは片端がパッド、片端がビア
    # 基板内に収まっているか
    for it in items:
        pts = [it["a"], it["b"]] if it["kind"] == "seg" else [it["c"]]
        for x, y in pts:
            if not (1 <= x <= BOARD_W - 1 and 1 <= y <= BOARD_H - 1):
                errs.append(f"near/outside board edge: {it['id']}")
    return errs


# ---------------------------------------------------------------- PCB 出力
def nc_name(ref, fpn, num, nets):
    """回路図で No-Connect の端子は、KiCad が付ける unconnected-(REF-PIN-PadN) 名を使う。"""
    if ref == "J1":
        pin = f"Pin_{num}"
    elif ref == "U1":
        pin = _U1_NAMES[int(num)][0]
    elif ref == "U2":
        pin = _U2_NAMES[int(num)][0]
    else:
        return ""
    return f"unconnected-({ref}-{pin.replace('/', '{slash}')}-Pad{num})"


def pcb_text() -> str:
    o = []
    A = o.append
    A('(kicad_pcb (version 20240108) (generator "pcbnew") (generator_version "8.0")')
    A('  (general (thickness 1.6) (legacy_teardrops no))')
    A('  (paper "A4")')
    A('  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (32 "B.Adhes" user "B.Adhesive") (33 "F.Adhes" user "F.Adhesive")'
      ' (34 "B.Paste" user) (35 "F.Paste" user) (36 "B.SilkS" user "B.Silkscreen") (37 "F.SilkS" user "F.Silkscreen")'
      ' (38 "B.Mask" user) (39 "F.Mask" user) (44 "Edge.Cuts" user) (45 "Margin" user)'
      ' (46 "B.CrtYd" user "B.Courtyard") (47 "F.CrtYd" user "F.Courtyard") (48 "B.Fab" user) (49 "F.Fab" user))')
    A('  (setup (pad_to_mask_clearance 0.05) (tenting front back))')  # マスク拡張 0.05mm、ビアはマスクで覆う
    for ref, _v, _s, fpn, _sp, _pc, nets in PARTS:
        for pd in fp_pads(fpn):
            nm = pad_net(ref, fpn, pd["num"], nets)
            if nm and nm not in NID:
                NID[nm] = len(NID)
    for name, n in sorted(NID.items(), key=lambda kv: kv[1]):
        A(f'  (net {n} "{name}")')

    sch_uuid = {r: U("sym-" + r) for r, *_ in PARTS}
    for ref, value, _s, fpn, _sp, at, nets in PARTS:
        A("  " + KL.embed_fp(fpn, ref, value, at, lambda tag, ref=ref: U(f"fp-{ref}-{tag}"),
                              lambda num, ref=ref, fpn=fpn, nets=nets: (lambda n: (NID[n], n) if n else None)(pad_net(ref, fpn, num, nets)),
                              sch_uuid[ref], dnp="DNP" in value))
    A(f'  (gr_rect (start 0 0) (end {BOARD_W} {BOARD_H}) (stroke (width 0.1) (type default)) (fill none) (layer "Edge.Cuts") (uuid "{U("edge")}"))')
    for k, (txt, x, y) in enumerate([("JJY HAT 60/40kHz", 35, 42.8), ("GPIO18 CARRIER", 35, 44.4), ("GPIO23 LEVEL", 35, 46.0),
                                     ("GPIO26 40k SEL", 35, 47.6), ("ANT", 50, 33.8), ("Rev B", 56, 12),
                                     ("RTC DS3231 + CR2032", 3.2, 10.5)]):
        A(f'  (gr_text "{txt}" (at {x} {y}) (layer "F.SilkS") (uuid "{U(f"txt{k}")}") (effects (font (size 1 1) (thickness 0.16)) (justify left)))')
    for k, (net, layer, w, a, b) in enumerate(TRACKS):
        A(f'  (segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width {w}) (layer "{layer}") (net {NID[net]}) (uuid "{U(f"trk{k}")}"))')
    for k, (net, x, y) in enumerate(VIAS):
        A(f'  (via (at {x} {y}) (size {VIA_D}) (drill {VIA_DRILL}) (layers "F.Cu" "B.Cu") (net {NID[net]}) (uuid "{U(f"via{k}")}"))')
    for layer in ("F.Cu", "B.Cu"):
        A(f'  (zone (net {NID["GND"]}) (net_name "GND") (layer "{layer}") (uuid "{U("zone" + layer)}") (hatch edge 0.5)'
          ' (connect_pads (clearance 0.3)) (min_thickness 0.25) (filled_areas_thickness no)'
          ' (fill (thermal_gap 0.5) (thermal_bridge_width 0.5))'
          f' (polygon (pts (xy 0.5 0.5) (xy {BOARD_W - 0.5} 0.5) (xy {BOARD_W - 0.5} {BOARD_H - 0.5}) (xy 0.5 {BOARD_H - 0.5}))))')
    A(')')
    return "\n".join(o) + "\n"


# ---------------------------------------------------------------- 回路図 出力
def E(size=1.27, hide=False, justify=None):
    j = f" (justify {justify})" if justify else ""
    return f'(effects (font (size {size} {size})){j}{" hide" if hide else ""})'


STROKE = '(stroke (width 0.254) (type default))'
NOFILL = '(fill (type none))'

# 記号ごとのピン: 番号 -> (名前, 型, x_lib, y_lib, angle, length)
# 標準ライブラリの記号はライブラリから読む。JJY ライブラリ(自作3点)だけ下で定義する。
JJY_LIBS = ("JJY:74LVC125", "JJY:DS3231SN", "JJY:AQY212S")
POWER_LIBS = ("power:GND", "power:+3V3", "power:PWR_FLAG")
SYM_PINS = {lib: KL.sym_pins(lib)
            for lib in sorted({p[2] for p in PARTS if p[2] not in JJY_LIBS} | set(POWER_LIBS))}
SYM_PINS["JJY:AQY212S"] = {"1": ("LED+", "passive", -7.62, 2.54, 0, 2.54), "2": ("LED-", "passive", -7.62, -2.54, 0, 2.54),
                           "3": ("A", "passive", 7.62, 2.54, 180, 2.54), "4": ("B", "passive", 7.62, -2.54, 180, 2.54)}
_U1_NAMES = {1: ("~{1OE}", "input"), 2: ("1A", "input"), 3: ("1Y", "output"), 4: ("~{2OE}", "input"), 5: ("2A", "input"),
             6: ("2Y", "output"), 7: ("GND", "power_in"), 8: ("3Y", "output"), 9: ("3A", "input"), 10: ("~{3OE}", "input"),
             11: ("4Y", "output"), 12: ("4A", "input"), 13: ("~{4OE}", "input"), 14: ("VCC", "power_in")}
SYM_PINS["JJY:74LVC125"] = {}
for n, (nm, ty) in _U1_NAMES.items():
    if n <= 7:
        SYM_PINS["JJY:74LVC125"][str(n)] = (nm, ty, -10.16, 7.62 - 2.54 * (n - 1), 0, 2.54)
    else:
        SYM_PINS["JJY:74LVC125"][str(n)] = (nm, ty, 10.16, 7.62 - 2.54 * (14 - n), 180, 2.54)

_U2_NAMES = {1: ("32KHZ", "output"), 2: ("VCC", "power_in"), 3: ("~{INT}/SQW", "output"), 4: ("~{RST}", "passive"),
             13: ("GND", "power_in"), 14: ("VBAT", "passive"), 15: ("SDA", "passive"), 16: ("SCL", "input")}
for n in range(5, 13):
    _U2_NAMES[n] = ("N.C.", "no_connect")
SYM_PINS["JJY:DS3231SN"] = {}
for n, (nm, ty) in _U2_NAMES.items():
    if n <= 8:
        SYM_PINS["JJY:DS3231SN"][str(n)] = (nm, ty, -10.16, 8.89 - 2.54 * (n - 1), 0, 2.54)
    else:
        SYM_PINS["JJY:DS3231SN"][str(n)] = (nm, ty, 10.16, 8.89 - 2.54 * (16 - n), 180, 2.54)

SYM_BODY = {
    "JJY:AQY212S": f'(rectangle (start -5.08 5.08) (end 5.08 -5.08) {STROKE} (fill (type background)))',
    "JJY:DS3231SN": f'(rectangle (start -7.62 11.43) (end 7.62 -11.43) {STROKE} (fill (type background)))',
    "JJY:74LVC125": f'(rectangle (start -7.62 10.16) (end 7.62 -10.16) {STROKE} (fill (type background)))',
}
SYM_REFP = {"JJY:AQY212S": "K", "JJY:DS3231SN": "U", "JJY:74LVC125": "U"}


def lib_symbol(lib_id: str, prefixed: bool = True) -> str:
    """JJY ライブラリの自作記号。prefixed=False はライブラリファイル用(名前にライブラリ名を付けない)。"""
    name = lib_id.split(":")[1]
    pins = []
    for num, (pname, ptype, x, y, ang, ln) in SYM_PINS[lib_id].items():
        pins.append(f'(pin {ptype} line (at {x} {y} {ang}) (length {ln}) (name "{pname}" {E()}) (number "{num}" {E()}))')
    return (f'(symbol "{lib_id if prefixed else name}" (pin_names (offset 1.016)) (exclude_from_sim no) (in_bom yes) (on_board yes)'
            f' (property "Reference" "{SYM_REFP[lib_id]}" (at 2.54 0 0) {E()})'
            f' (property "Value" "{name}" (at 0 0 0) {E()})'
            f' (property "Footprint" "" (at 0 0 0) {E(hide=True)})'
            f' (property "Datasheet" "~" (at 0 0 0) {E(hide=True)})'
            f' (symbol "{name}_0_1" {SYM_BODY[lib_id]})'
            f' (symbol "{name}_1_1" {" ".join(pins)}))')


def jjy_lib_text() -> str:
    body = "\n".join("  " + lib_symbol(l, prefixed=False) for l in JJY_LIBS)
    head = '(kicad_symbol_lib (version 20240108) (generator "kicad_symbol_editor") (generator_version "8.0")\n'
    return head + body + "\n)\n"


SYM_LIB_TABLE = ('(sym_lib_table\n  (version 7)\n'
                 '  (lib (name "JJY")(type "KiCad")(uri "${KIPRJMOD}/JJY.kicad_sym")(options "")(descr "JJY HAT custom symbols"))\n)\n')


def sch_text() -> str:
    o = []
    A = o.append
    cnt = {"pwr": 0, "flg": 0, "n": 0}

    def uid(tag):
        cnt["n"] += 1
        return U(f"sch-{tag}-{cnt['n']}")

    def wire(a, b):
        A(f'  (wire (pts (xy {a[0]:.2f} {a[1]:.2f}) (xy {b[0]:.2f} {b[1]:.2f})) (stroke (width 0) (type default)) (uuid "{uid("w")}"))')

    def power_sym(kind, pos, direction, flag=False):
        cnt["pwr"] += 1
        # GND: 図形は下向き / +3V3: 図形は上向き。引き出し方向に合わせて回転する。
        base_down = kind == "GND"
        angle = {"down": 0 if base_down else 180, "up": 180 if base_down else 0,
                 "right": 90 if base_down else 270, "left": 270 if base_down else 90}[direction]
        val = "GND" if kind == "GND" else "+3V3"
        ref = f"#PWR{cnt['pwr']:02d}"
        A(f'  (symbol (lib_id "power:{val}") (at {pos[0]:.2f} {pos[1]:.2f} {angle}) (unit 1) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no) (uuid "{uid("pw")}")'
          f' (property "Reference" "{ref}" (at {pos[0]:.2f} {pos[1]:.2f} 0) {E(hide=True)})'
          f' (property "Value" "{val}" (at {pos[0] + 2.54:.2f} {pos[1]:.2f} 0) {E(hide=True)})'
          f' (property "Footprint" "" (at {pos[0]:.2f} {pos[1]:.2f} 0) {E(hide=True)})'
          f' (property "Datasheet" "" (at {pos[0]:.2f} {pos[1]:.2f} 0) {E(hide=True)})'
          f' (pin "1" (uuid "{uid("pwp")}"))'
          f' (instances (project "{PROJ}" (path "/{ROOT_UUID}" (reference "{ref}") (unit 1)))))')
        if flag:
            cnt["flg"] += 1
            ref = f"#FLG{cnt['flg']:02d}"
            A(f'  (symbol (lib_id "power:PWR_FLAG") (at {pos[0]:.2f} {pos[1]:.2f} 0) (unit 1) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no) (uuid "{uid("fl")}")'
              f' (property "Reference" "{ref}" (at {pos[0]:.2f} {pos[1]:.2f} 0) {E(hide=True)})'
              f' (property "Value" "PWR_FLAG" (at {pos[0]:.2f} {pos[1]:.2f} 0) {E(hide=True)})'
              f' (property "Footprint" "" (at {pos[0]:.2f} {pos[1]:.2f} 0) {E(hide=True)})'
              f' (property "Datasheet" "~" (at {pos[0]:.2f} {pos[1]:.2f} 0) {E(hide=True)})'
              f' (pin "1" (uuid "{uid("flp")}"))'
              f' (instances (project "{PROJ}" (path "/{ROOT_UUID}" (reference "{ref}") (unit 1)))))')

    def label(name, pos, direction):
        ang, j = {"right": (0, "left bottom"), "left": (180, "right bottom"), "up": (90, "left bottom"), "down": (270, "right bottom")}[direction]
        A(f'  (label "{name}" (at {pos[0]:.2f} {pos[1]:.2f} {ang}) {E(justify=j)} (uuid "{uid("l")}"))')

    flags = {"GND": True, "+3V3": True}  # 各電源ネットに PWR_FLAG を1個

    def attach(pin_pos, outward, net):
        """ピン端から 2.54 の引き出し線 + ラベル/電源記号。net=='' なら No-Connect。"""
        dx, dy = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}[outward]
        if net == "":
            A(f'  (no_connect (at {pin_pos[0]:.2f} {pin_pos[1]:.2f}) (uuid "{uid("nc")}"))')
            return
        end = (pin_pos[0] + dx * 2.54, pin_pos[1] + dy * 2.54)
        wire(pin_pos, end)
        if net in ("GND", "+3V3"):
            power_sym("GND" if net == "GND" else "3V3", end, outward, flag=flags.pop(net, False))
        else:
            label(SCH_NAME[net], end, outward)

    A(f'(kicad_sch (version 20231120) (generator "eeschema") (generator_version "8.0") (uuid "{ROOT_UUID}") (paper "A3")')
    A(f'  (title_block (title "JJY HAT 40/60kHz for Raspberry Pi 4") (date "2026-10-29") (rev "B")'
      ' (comment 1 "Raspberry Pi 4 GPIO18 (PWM0) = carrier, GPIO23 = level (low = full amplitude)"))')
    used = sorted({p[2] for p in PARTS} | set(POWER_LIBS))
    A("  (lib_symbols")
    for lib in used:
        A("    " + (lib_symbol(lib) if lib in JJY_LIBS else KL.embed_sym(lib)))
    A("  )")

    for ref, value, lib, fpn, (sx, sy), _pcb, nets in PARTS:
        _sym = None if lib in JJY_LIBS else KL.load_sym(lib)
        _bom = (KL.kid(_sym, "in_bom") or ["", "yes"])[1] if _sym else "yes"
        _brd = (KL.kid(_sym, "on_board") or ["", "yes"])[1] if _sym else "yes"
        A(f'  (symbol (lib_id "{lib}") (at {sx} {sy} 0) (unit 1) (exclude_from_sim no) (in_bom {_bom}) (on_board {_brd})'
          f' (dnp {"yes" if "DNP" in value else "no"}) (uuid "{U("sym-" + ref)}")'
          f' (property "Reference" "{ref}" (at {sx + 3.81} {sy - 2.54} 0) {E(justify="left")})'
          f' (property "Value" "{value}" (at {sx + 3.81} {sy} 0) {E(justify="left")})'
          f' (property "Footprint" "{fpn}" (at {sx} {sy} 0) {E(hide=True)})'
          f' (property "Datasheet" "~" (at {sx} {sy} 0) {E(hide=True)})')
        for num in SYM_PINS[lib]:
            A(f'    (pin "{num}" (uuid "{U(f"sp-{ref}-{num}")}"))')
        A(f'    (instances (project "{PROJ}" (path "/{ROOT_UUID}" (reference "{ref}") (unit 1)))))')

    for ref, value, lib, fpn, (sx, sy), _pcb, nets in PARTS:
        for num, (pname, ptype, x, y, ang, ln) in SYM_PINS[lib].items():
            outward = {0: "left", 180: "right", 270: "up", 90: "down"}[ang]
            pos = (sx + x, sy - y)
            net = nets.get(int(num), "")
            attach(pos, outward, net)

    def note(text, x, y, size=2.0):
        A(f'  (text "{text}" (exclude_from_sim no) (at {x} {y} 0) {E(size=size, justify="left")} (uuid "{uid("t")}"))')

    note("JJY HAT 40/60kHz (60kHz Hagane-yama default / 40kHz Ohtakadoya-yama), on-board RTC", 20, 25, 3.5)
    note("GPIO18 (PWM0) = 40k/60kHz carrier. GPIO23 = level: Low -> U1B enabled -> full amplitude / High -> 10% (-20dB).", 20, 35)
    note("U1A (always on) drives via R1 1k, U1B adds R2 100R in parallel: (1k+Rcoil)/(91R+Rcoil) = ~10:1.", 20, 41)
    note("Series resonance: L(1mH) with C2+C3+C4 (+C5 trim) = 7.05nF -> 59.9kHz; with C7+C8+C9 (+9.1nF) = 16.15nF -> 39.6kHz. Measure L and tune C.", 20, 47)
    note("U2 DS3231SN + BT1 CR2032: on-board RTC (I2C pull-ups are on the Pi). Enable [rtc] in /etc/jjyd.toml.", 20, 59)
    note("Band select: GPIO26 (FSEL). Low = 60kHz (default). High = K1 photo-MOS relay adds C7-C9 (9.1nF) -> 40kHz.", 20, 65)
    note("Keep the radiated field within the micro-power station limit (500uV/m at 3m, below 322MHz).", 20, 53)
    A('  (sheet_instances (path "/" (page "1")))')
    A(')')
    return "\n".join(o) + "\n"


def pro_text() -> str:
    return json.dumps({
        "meta": {"filename": f"{PROJ}.kicad_pro", "version": 1},
        "net_settings": {"classes": [{"name": "Default", "clearance": 0.2, "track_width": 0.25,
                                      "via_diameter": VIA_D, "via_drill": VIA_DRILL}],
                         "meta": {"version": 3}},
        "board": {"design_settings": {"rules": {"min_clearance": 0.2, "min_track_width": 0.2}}},
    }, indent=2) + "\n"


def main() -> int:
    snap_tracks()
    errs = check()
    if errs:
        print("LAYOUT CHECK FAILED:")
        print("\n".join("  " + e for e in errs))
        return 1
    (OUT / f"{PROJ}.kicad_pcb").write_text(pcb_text(), encoding="utf-8")
    (OUT / f"{PROJ}.kicad_sch").write_text(sch_text(), encoding="utf-8")
    (OUT / f"{PROJ}.kicad_pro").write_text(pro_text(), encoding="utf-8")
    (OUT / "JJY.kicad_sym").write_text(jjy_lib_text(), encoding="utf-8")
    (OUT / "sym-lib-table").write_text(SYM_LIB_TABLE, encoding="utf-8")
    print(f"layout check OK; wrote {PROJ}.kicad_pro/.kicad_sch/.kicad_pcb to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
