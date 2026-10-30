"""KiCad 標準ライブラリ(フットプリント/シンボル)を読み込み、基板/回路図へ埋め込むための補助。

標準ライブラリの実物をそのまま埋め込むことで、DRC/ERC の「ライブラリのコピーと一致しない」警告を避ける。
"""
import copy
import os
import re
from functools import lru_cache
from pathlib import Path

SHARE = Path(os.environ.get("KICAD_SHARE") or r"C:\Program Files\KiCad\10.0\share\kicad")


class Q(str):
    """引用符つき文字列。"""


_TOK = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def parse(text: str):
    stack = [[]]
    for m in _TOK.finditer(text):
        t = m.group(0)
        if t == "(":
            stack.append([])
        elif t == ")":
            n = stack.pop()
            stack[-1].append(n)
        elif t[0] == '"':
            stack[-1].append(Q(t[1:-1].replace('\\"', '"').replace("\\\\", "\\")))
        else:
            stack[-1].append(t)
    return stack[0][0]


def dump(node) -> str:
    if isinstance(node, list):
        return "(" + " ".join(dump(c) for c in node) + ")"
    if isinstance(node, Q):
        return '"' + str(node).replace("\\", "\\\\").replace('"', '\\"') + '"'
    return str(node)


def kids(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def kid(node, name):
    k = kids(node, name)
    return k[0] if k else None


# ---------------------------------------------------------------- フットプリント
LOCAL_FP = {}  # プロジェクト内フットプリントライブラリ: {"JJY": Path(...pretty)}


@lru_cache(maxsize=None)
def load_fp(fp_id: str):
    lib, name = fp_id.split(":")
    base = LOCAL_FP.get(lib) or (SHARE / "footprints" / f"{lib}.pretty")
    return parse((base / f"{name}.kicad_mod").read_text(encoding="utf-8"))


def pad_infos(fp_id: str):
    """パッド情報: dict(num, type, shape, x, y, angle, w, h, drill)。"""
    out = []
    for p in kids(load_fp(fp_id), "pad"):
        at = kid(p, "at")
        size = kid(p, "size")
        drill = kid(p, "drill")
        d = None
        if drill:
            nums = [float(x) for x in drill[1:] if re.fullmatch(r"-?[\d.]+", str(x))]
            d = nums[0] if nums else None
        out.append(dict(num=str(p[1]), type=p[2], shape=p[3], x=float(at[1]), y=float(at[2]),
                        angle=float(at[3]) if len(at) > 3 else 0.0,
                        w=float(size[1]), h=float(size[2]), drill=d))
    return out


def _num(x: float) -> str:
    return f"{x:.6f}".rstrip("0").rstrip(".") or "0"


def embed_fp(fp_id, ref, value, at, uuid_fn, net_of, sch_path_uuid, dnp=False, ref_text=None):
    """ライブラリのフットプリントを基板用に変換して文字列で返す。

    at: (x, y, 回転角)  uuid_fn(tag) -> uuid 文字列  net_of(pad番号) -> (net番号, ネット名) | None
    """
    x, y, rot = at
    t = copy.deepcopy(load_fp(fp_id))
    t[1] = Q(fp_id)
    t[:] = [c for c in t if not (isinstance(c, list) and c and c[0] in ("version", "generator", "generator_version"))]
    layer_i = next(i for i, c in enumerate(t) if isinstance(c, list) and c and c[0] == "layer")
    pos = ["at", _num(x), _num(y)] + ([_num(rot)] if rot else [])
    t[layer_i + 1:layer_i + 1] = [["uuid", Q(uuid_fn("fp"))], pos]
    n = 0
    for c in t:
        if not isinstance(c, list) or not c:
            continue
        if c[0] == "property" and c[1] == "Reference":
            c[2] = Q(ref)
            if ref_text == "hide":
                c.insert(-1, ["hide", "yes"])
            elif ref_text:
                at = kid(c, "at")
                at[1:] = [_num(ref_text[0]), _num(ref_text[1]), _num(ref_text[2])]
                kid(c, "layer")[1] = Q("F.SilkS")
                kid(kid(kid(c, "effects"), "font"), "thickness")[1] = "0.16"
            else:
                kid(c, "layer")[1] = Q("F.Fab")
        elif c[0] == "property" and c[1] == "Value":
            c[2] = Q(value)
            if not kid(c, "hide"):
                c.insert(-1, ["hide", "yes"])  # 値は図面(README/BOM)で確認できるので基板上では隠す
        elif c[0] == "attr" and dnp:
            c.append("dnp")
        elif c[0] in ("fp_line", "fp_rect", "fp_circle", "fp_arc", "fp_poly", "fp_curve", "fp_text", "pad"):
            n += 1
            if c[0] == "fp_text" and c[1] == "user" and "${REFERENCE}" in str(c[2]) and not kid(c, "hide"):
                c.insert(-1, ["hide", "yes"])  # Fab 層の部品番号の重複表示(基板上の番号と重なる)を隠す
            lay = kid(c, "layer")
            if lay and "SilkS" in str(lay[1]) and kid(c, "stroke"):  # 製造業者の最小線幅(0.15mm)に合わせて太くする
                w = kid(kid(c, "stroke"), "width")
                if float(w[1]) < 0.16:
                    w[1] = "0.16"
            if c[0] == "pad":
                a = kid(c, "at")
                ang = ((float(a[3]) if len(a) > 3 else 0.0) + rot) % 360
                del a[3:]
                if ang:
                    a.append(_num(ang))
                nt = net_of(str(c[1]))
                if nt:
                    c.append(["net", str(nt[0]), Q(nt[1])])
            c.append(["uuid", Q(uuid_fn(f"c{n}"))])
    path_i = max(i for i, c in enumerate(t) if isinstance(c, list) and c and c[0] == "property") + 1
    t.insert(path_i, ["path", Q("/" + sch_path_uuid)])
    return dump(t)


# ---------------------------------------------------------------- シンボル
@lru_cache(maxsize=None)
def _sym_lib(lib: str):
    root = parse((SHARE / "symbols" / f"{lib}.kicad_sym").read_text(encoding="utf-8"))
    return {str(c[1]): c for c in kids(root, "symbol")}


def load_sym(lib_id: str):
    lib, name = lib_id.split(":")
    return _sym_lib(lib)[name]


def sym_pins(lib_id: str):
    """番号 -> (名前, 型, x, y, 角度, 長さ)。ユニット 0(共通)と 1 のピンを集める。"""
    out = {}
    for sub in kids(load_sym(lib_id), "symbol"):
        for p in kids(sub, "pin"):
            at = kid(p, "at")
            out[str(kid(p, "number")[1])] = (str(kid(p, "name")[1]), p[1], float(at[1]), float(at[2]),
                                             int(float(at[3])), float(kid(p, "length")[1]))
    return out


def embed_sym(lib_id: str) -> str:
    t = copy.deepcopy(load_sym(lib_id))
    t[1] = Q(lib_id)
    return dump(t)
