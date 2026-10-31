"""モニタが画面に出す情報の取得(jjyd の状態ファイル、chrony、システム)。取得に失敗した項目は None にして、画面側で「--」にする。"""
import json
import os
import subprocess
import time

STALE_S = 12.0  # 状態ファイルがこれより古ければ jjyd が動いていないとみなす(呼出符号の 9 秒間は書かれない)


def read_status(path: str, now: float | None = None) -> dict | None:
    """jjyd の状態ファイル。無い・壊れている・古いときは None。"""
    now = time.time() if now is None else now
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict) or abs(now - float(d["time"])) > STALE_S:
            return None
        return d
    except (OSError, ValueError, KeyError, TypeError):
        return None


def parse_tracking(line: str) -> dict:
    """`chronyc -c tracking` の 1 行。"""
    f = line.strip().split(",")
    return {"refid": f[0], "ref": f[1], "stratum": int(f[2]), "ref_time": float(f[3]),
            "offset": float(f[4]), "last_offset": float(f[5]), "rms": float(f[6]), "freq_ppm": float(f[7]),
            "skew_ppm": float(f[9]), "root_delay": float(f[10]), "root_disp": float(f[11]),
            "interval": float(f[12]), "leap": f[13]}


def parse_sources(text: str) -> list[dict]:
    """`chronyc -c sources` の全行。state: * 選択中, + 結合, - 除外, ? 到達不能, x 不正, ~ ばらつき大。"""
    out = []
    for line in text.strip().splitlines():
        f = line.split(",")
        if len(f) < 10:
            continue
        out.append({"mode": f[0], "state": f[1], "name": f[2], "stratum": int(f[3]), "poll": int(f[4]),
                    "reach": int(f[5], 8), "last_rx": int(f[6]), "offset": float(f[7]), "error": float(f[9])})
    return out


def _run(*cmd, timeout=3) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _first_ipv4() -> str | None:
    out = _run("hostname", "-I")
    for a in (out or "").split():
        if a.count(".") == 3:
            return a
    return None


def _file(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


def collect() -> dict:
    """時間のかかる取得(外部コマンド)をまとめて行う。画面の更新とは別のスレッドから呼ぶ。"""
    d: dict = {"tracking": None, "sources": [], "services": {}, "host": os.uname().nodename if hasattr(os, "uname") else None,
               "ip": _first_ipv4(), "temp_c": None, "load": None, "uptime_s": None}
    try:
        t = _run("chronyc", "-c", "tracking")
        d["tracking"] = parse_tracking(t) if t else None
        d["sources"] = parse_sources(_run("chronyc", "-c", "sources") or "")
    except (ValueError, IndexError):
        pass
    for unit in ("jjyd", "chrony"):
        d["services"][unit] = (_run("systemctl", "is-active", unit) or "inactive").strip() or "unknown"
    temp = _file("/sys/class/thermal/thermal_zone0/temp")
    d["temp_c"] = int(temp) / 1000 if temp and temp.strip().isdigit() else None
    up = _file("/proc/uptime")
    d["uptime_s"] = float(up.split()[0]) if up else None
    if hasattr(os, "getloadavg"):
        d["load"] = os.getloadavg()[0]
    return d
