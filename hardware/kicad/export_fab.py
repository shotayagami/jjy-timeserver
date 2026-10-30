"""設計から発注データ一式を作り直す: gen_kicad -> ゾーン塗り -> ガーバー/ドリル/BOM/CPL -> JLCPCB 用 BOM/CPL。

    python -I export_fab.py     (kicad-cli が PATH に無ければ KICAD_CLI 環境変数で指定)
"""
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAB = HERE / "fab"
K = os.environ.get("KICAD_CLI") or shutil.which("kicad-cli") or r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"


def run(*a):
    r = subprocess.run([K, *map(str, a)], capture_output=True, text=True)
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "", r.stderr.strip()[-200:])
    if r.returncode:
        sys.exit(f"kicad-cli failed: {a[:3]}")


def main():
    subprocess.run([sys.executable, "-I", str(HERE / "gen_kicad.py")], check=True)
    shutil.rmtree(FAB / "gerber", ignore_errors=True)
    (FAB / "gerber").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        for f in ("jjy-hat.kicad_pcb", "jjy-hat.kicad_pro", "jjy-hat.kicad_sch", "fp-lib-table", "sym-lib-table", "JJY.kicad_sym"):
            shutil.copy(HERE / f, t)
        shutil.copytree(HERE / "JJY.pretty", Path(t) / "JJY.pretty")
        pcb = Path(t) / "jjy-hat.kicad_pcb"
        run("pcb", "drc", pcb, "-o", Path(t) / "drc.rpt", "--refill-zones", "--save-board", "--severity-error")
        g = FAB / "gerber"
        run("pcb", "export", "gerbers", pcb, "-o", str(g) + os.sep, "--layers",
            "F.Cu,B.Cu,F.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts", "--subtract-soldermask")
        run("pcb", "export", "drill", pcb, "-o", str(g) + os.sep, "--format", "excellon", "--drill-origin", "absolute",
            "--excellon-units", "mm", "--excellon-separate-th")
        run("pcb", "export", "pos", pcb, "-o", FAB / "jjy-hat-pos.csv", "--format", "csv", "--units", "mm",
            "--side", "front", "--exclude-dnp")
    run("sch", "export", "bom", HERE / "jjy-hat.kicad_sch", "-o", FAB / "jjy-hat-bom.csv", "--fields",
        "Reference,Value,Footprint,${QUANTITY}", "--labels", "Designator,Value,Footprint,Qty",
        "--group-by", "Value,Footprint", "--exclude-dnp")
    with zipfile.ZipFile(FAB / "jjy-hat-gerber.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(g.glob("*")):
            if "_map" not in f.name:
                z.write(f, f.name)
    subprocess.run([sys.executable, "-I", str(HERE / "make_jlcpcb.py")], check=True)


if __name__ == "__main__":
    main()
