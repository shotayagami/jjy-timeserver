"""KiCad の出力から JLCPCB 組立用の BOM / CPL を作る。

    python make_jlcpcb.py   (事前に fab/jjy-hat-pos.csv が kicad-cli で出力済みであること)

SMT 実装するのは表面実装部品のみ。J1/J2 はスルーホールなので実装対象外(手はんだ)。
"""
import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAB = HERE / "fab"
OUT = FAB / "jlcpcb"

# 値 -> (LCSC 品番, 部品名)。品番は fab/README.md に確認内容を記載
LCSC = {
    "74LVC125": ("C7661", "SN74LVC125ADR"),
    "DS3231SN#": ("C722469", "DS3231SN#"),
}
THT_REFS = {"J1", "BT1", "R1", "R2", "R3", "R4", "R5", "D1", "C1", "C6", "J3", "R7", "D2", "R8", "D3", "L1", "JP1", "J2", "JP2", "C2", "C3", "C4", "C5", "C7", "C8", "C9", "R6"}  # リード部品は手はんだ
# JLCPCB の部品ライブラリの基準向きとのずれ(度)。プレビューで確認して調整する。
ROT_OFFSET = {"U1": 0}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    rows = list(csv.DictReader((FAB / "jjy-hat-pos.csv").open(encoding="utf-8")))
    smt = [r for r in rows if r["Ref"] not in THT_REFS]

    groups: dict[str, list[dict]] = {}
    for r in smt:
        groups.setdefault(r["Val"], []).append(r)
    with (OUT / "bom.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for val, rs in groups.items():
            lcsc, _mfr = LCSC[val]
            w.writerow([val, ",".join(sorted(r["Ref"] for r in rs)), rs[0]["Package"], lcsc])
    with (OUT / "cpl.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for r in smt:
            rot = (float(r["Rot"]) + ROT_OFFSET.get(r["Ref"], 0)) % 360
            w.writerow([r["Ref"], f"{float(r['PosX']):.4f}mm", f"{float(r['PosY']):.4f}mm", "Top", f"{rot:g}"])
    missing = [v for v in groups if not LCSC[v][0]]
    print(f"wrote {OUT}/bom.csv, cpl.csv ({len(smt)} parts)" + (f"; MISSING LCSC: {missing}" if missing else ""))


if __name__ == "__main__":
    main()
