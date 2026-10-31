"""Raspberry Pi の画面に出すモニタ。jjyd の送信(パルス・フレーム・基板の LED)と、chrony の同期状態を表示する。

    python3 -m jjymon                 全画面(Esc で終了、F11 で全画面の切替)
    python3 -m jjymon --windowed      1280x720 の窓

jjyd の状態ファイル(/run/jjyd/status.json)と chronyc、/proc・/sys を読むだけで、何も操作しない。
"""
import argparse
import threading
import time
import tkinter as tk
import tkinter.font as tkfont

from . import data, emulate, frame as fr

W, H = 1920, 1080  # 設計上の画面。実際の大きさに合わせて拡縮する
JST_S = 9 * 3600
WAVE_S = 10.0

BG, PANEL, CELL, EDGE = "#0e1318", "#171f27", "#1f2a35", "#2b3946"
TEXT, DIM = "#e4ebf1", "#8795a3"
OK, BAD, WARN = "#3ecf6e", "#ff5c5c", "#f0c040"
SYM_COLOR = {"M": "#f0a030", "1": "#38b6e8", "0": "#8aa0b8", "C": "#d070e0"}
SYM_DARK = {"M": "#6b4a1c", "1": "#1b4f67", "0": "#36444f", "C": "#5a3563"}
LED_ON = {"d1": "#ff3b3b", "d2": "#9be83a", "d3": "#ffcc33"}
LED_OFF = {"d1": "#3a1c1c", "d2": "#27381a", "d3": "#3a3118"}
WEEK = "月火水木金土日"


def fmt_dur(s: float | None) -> str:
    if s is None:
        return "--"
    s = int(s)
    if s >= 86400:
        return f"{s // 86400}日{s % 86400 // 3600}時間"
    if s >= 3600:
        return f"{s // 3600}時間{s % 3600 // 60}分"
    if s >= 60:
        return f"{s // 60}分{s % 60}秒"
    return f"{s}秒"


def fmt_ms(sec: float | None, signed=True) -> str:
    return "--" if sec is None else f"{sec * 1000:{'+' if signed else ''}.3f} ms"


class Monitor:
    def __init__(self, root: tk.Tk, status_path: str):
        self.root, self.status_path = root, status_path
        self.cv = tk.Canvas(root, bg=BG, highlightthickness=0, cursor="none")
        self.cv.pack(fill="both", expand=True)
        self.info: dict = {}
        self.status: dict | None = None
        self.status_read = 0.0
        self.secs: dict = {}  # 秒 -> (シンボル, 秒の番号, 送信中か): 波形の描画用
        self.wave_carrier = False
        self.items: dict = {}
        self.cache: dict = {}
        self.fonts: dict = {}
        self.k = 1.0
        self.grid_key = None
        self.after_id = None
        self.cv.bind("<Configure>", self._on_resize)
        threading.Thread(target=self._collector, daemon=True).start()
        self._tick()

    # ---- 取得(別スレッド)
    def _collector(self) -> None:
        while True:
            try:
                self.info = data.collect()
            except Exception:  # 取得の失敗で画面を止めない
                pass
            time.sleep(2)

    # ---- 描画の部品
    def font(self, px: float, bold=False, mono=False) -> tkfont.Font:
        key = (round(px * self.k), bold, mono)
        if key not in self.fonts:
            self.fonts[key] = tkfont.Font(family="DejaVu Sans Mono" if mono else "Droid Sans Fallback",
                                          size=-max(8, key[0]), weight="bold" if bold else "normal")
        return self.fonts[key]

    def s(self, v: float) -> float:
        return v * self.k

    def panel(self, x, y, w, h, title) -> None:
        s = self.s
        self.cv.create_rectangle(s(x), s(y), s(x + w), s(y + h), fill=PANEL, outline=EDGE, width=1)
        self.cv.create_text(s(x + 16), s(y + 10), text=title, anchor="nw", fill=DIM, font=self.font(22))

    def text(self, key, x, y, text="", px=26, fill=TEXT, anchor="nw", bold=False, mono=False) -> None:
        self.items[key] = self.cv.create_text(self.s(x), self.s(y), text=text, anchor=anchor, fill=fill,
                                              font=self.font(px, bold, mono))

    def label(self, x, y, text, px=24, fill=DIM, anchor="nw") -> None:
        self.cv.create_text(self.s(x), self.s(y), text=text, anchor=anchor, fill=fill, font=self.font(px))

    def set(self, key, text=None, fill=None) -> None:
        """値が変わったときだけ更新する(毎フレームの無駄な再描画を避ける)。"""
        if text is not None and self.cache.get((key, "t")) != text:
            self.cache[(key, "t")] = text
            self.cv.itemconfigure(self.items[key], text=text)
        if fill is not None and self.cache.get((key, "f")) != fill:
            self.cache[(key, "f")] = fill
            self.cv.itemconfigure(self.items[key], fill=fill)

    # ---- 画面の組み立て
    def _on_resize(self, _e) -> None:
        if self.after_id:
            self.root.after_cancel(self.after_id)
        self.after_id = self.root.after(150, self._build)

    def _build(self) -> None:
        self.after_id = None
        cv, s = self.cv, self.s
        w, h = max(cv.winfo_width(), 320), max(cv.winfo_height(), 240)
        self.k = min(w / W, h / H)
        cv.delete("all")
        self.items.clear()
        self.cache.clear()
        self.grid_key = None
        cv.create_rectangle(0, 0, w, h, fill=BG, outline="")

        # ヘッダ
        self.label(30, 14, "JJY 標準電波シミュレータ / タイムサーバ", 38, TEXT)
        self.text("host", W - 30, 22, "", 26, DIM, anchor="ne")

        # 時計
        self.panel(30, 80, 930, 340, "日本標準時 (JST)")
        self.text("date", 60, 120, "", 46)
        self.text("clock", 60, 175, "", 170, TEXT, bold=True, mono=True)
        self.text("utc", 60, 375, "", 26, DIM)

        # 送信状態 + 基板の LED
        self.panel(990, 80, 900, 340, "jjyd 送信")
        cv.create_rectangle(s(1010), s(120), s(1870), s(190), fill=CELL, outline=EDGE, tags="badge")
        self.items["badge"] = cv.find_withtag("badge")[0]
        self.text("state", 1440, 155, "", 42, TEXT, anchor="center", bold=True)
        self.text("sync1", 1010, 202, "", 24)
        self.text("sync2", 1010, 234, "", 22, DIM)
        # 基板の LED(縦に詰めて並べる)と、LCD(16x2)の再現
        for i, (name, cap, sub) in enumerate((("d1", "D1 赤", "高レベル"), ("d2", "D2 黄緑", "信号(低レベル)"),
                                              ("d3", "D3 黄", "通電"))):
            cy = 296 + i * 34
            self.items[name] = cv.create_oval(s(1022), s(cy - 12), s(1046), s(cy + 12), fill=LED_OFF[name],
                                              outline=EDGE, width=2)
            self.label(1060, cy, cap, 22, TEXT, "w")
            self.label(1170, cy, sub, 20, DIM, "w")
        self.label(1450, 268, "LCD(基板 J3)", 18, DIM)
        cv.create_rectangle(s(1450), s(290), s(1860), s(380), fill="#10285f", outline=EDGE, width=2)
        for row in range(2):
            for col in range(16):
                x, y = 1458 + col * 25, 296 + row * 40
                cv.create_rectangle(s(x), s(y), s(x + 23), s(y + 37), fill="#1d44a0", outline="#16347c")
                self.text(f"lcd{row}_{col}", x + 12, y + 19, "", 30, "#f2f6ff", anchor="center", bold=True, mono=True)
        self.text("edge", 1010, 394, "", 20, DIM)

        # フレーム全体と、各ビットの意味
        self.panel(30, 440, 1130, 360, "フレーム(1 分 = 60 秒)   高レベル: M 0.2 秒 / 1 0.5 秒 / 0 0.8 秒")
        self.text("minute", 1150, 450, "", 22, TEXT, anchor="ne")
        self.cells = []
        for i in range(61):
            x, y = 50 + (i % 10) * 68, 486 + (i // 10) * 44
            r = cv.create_rectangle(s(x), s(y), s(x + 62), s(y + 40), fill=CELL, outline=EDGE)
            b = cv.create_rectangle(s(x + 1), s(y + 36), s(x + 61), s(y + 39), fill=EDGE, outline="")
            t = cv.create_text(s(x + 22), s(y + 19), text="", fill=DIM, font=self.font(24, True, True))
            n = cv.create_text(s(x + 4), s(y + 2), text=str(i), anchor="nw", fill=DIM, font=self.font(12))
            wl = cv.create_text(s(x + 59), s(y + 34), text="", anchor="se", fill=DIM, font=self.font(14, False, True))
            if i == 60:
                for it in (r, b, t, n, wl):
                    cv.itemconfigure(it, state="hidden")
            self.cells.append((r, t, n, wl, b))
        self.legend = []
        for i, (key, name, secs) in enumerate(fr.ROWS):
            y = 486 + i * 24
            bg = cv.create_rectangle(s(750), s(y), s(1150), s(y + 23), fill=PANEL, outline="")
            cv.create_rectangle(s(758), s(y + 5), s(768), s(y + 17), fill=fr.COLOR[key], outline="")
            cv.create_text(s(776), s(y + 11), text=name, anchor="w", fill=TEXT, font=self.font(18))
            self.text("lg_" + key, 1146, y + 1, "", 18, TEXT, anchor="ne", mono=True)
            self.legend.append((key, bg))

        # 波形(直近 10 秒)
        self.panel(1180, 440, 710, 360, f"信号波形(直近 {int(WAVE_S)} 秒。右端が現在)")
        self.wx0, self.wx1 = 1340, 1870
        self.lanes = {"amp": (500, 590), "d1": (640, 680), "d2": (720, 760)}
        for name, (a, b) in self.lanes.items():
            cv.create_rectangle(s(self.wx0), s(a), s(self.wx1), s(b), fill=BG, outline=EDGE)
        self.label(1330, 505, "搬送波", 22, TEXT, "ne")
        self.label(1330, 535, "100%", 18, DIM, "ne")
        self.label(1330, 568, "10%", 18, DIM, "ne")
        self.label(1330, 650, "D1 赤", 22, "#ff7a7a", "ne")
        self.label(1330, 730, "D2 黄緑", 22, "#b6f060", "ne")
        self.grid_lines = [(cv.create_line(0, 0, 0, 0, fill=EDGE), cv.create_text(0, 0, fill=DIM, font=self.font(16), anchor="n"))
                           for _ in range(int(WAVE_S) + 2)]
        for name, color in (("amp", "#6ad6ff"), ("d1", "#ff5c5c"), ("d2", "#9be83a")):
            self.items["w_" + name] = cv.create_line(0, 0, 0, 0, fill=color, width=max(2, int(s(2))))

        # chrony
        self.panel(30, 820, 560, 240, "chrony(時刻の同期)")
        self.rows_n = ("ref", "off", "rms", "freq", "upd", "leap")
        for i, (key, lab) in enumerate(zip(self.rows_n, ("同期先", "システム時刻のずれ", "RMS", "周波数補正", "最終更新", "閏秒"))):
            self.label(50, 872 + i * 30, lab, 22)
            self.text("t_" + key, 570, 870 + i * 30, "", 24, TEXT, anchor="ne", mono=True)

        # 時刻源の一覧
        self.panel(610, 820, 830, 240, "時刻源")
        self.text("src_head", 630, 868, "", 19, DIM, mono=True)
        for i in range(6):
            self.text(f"src{i}", 630, 896 + i * 27, "", 19, TEXT, mono=True)

        # システム
        self.panel(1460, 820, 430, 240, "システム")
        for i, (key, lab) in enumerate((("jjyd", "jjyd"), ("chrony", "chrony"), ("temp", "CPU 温度"), ("load", "負荷"), ("up", "稼働"))):
            self.label(1480, 872 + i * 32, lab, 22)
            self.text("y_" + key, 1870, 870 + i * 32, "", 24, TEXT, anchor="ne", mono=True)

    # ---- 毎回の更新
    def _tick(self) -> None:
        try:
            if self.items:
                self._update(time.time())
        finally:
            self.root.after(16, self._tick)

    def _update(self, now: float) -> None:
        if now - self.status_read > 0.2:
            self.status, self.status_read = data.read_status(self.status_path, now), now
        st, info = self.status, self.info
        jst = time.gmtime(now + JST_S)
        minute_now = time.strftime("%Y-%m-%d %H:%M", jst)

        self.set("clock", time.strftime("%H:%M:%S", jst))
        self.set("date", time.strftime("%Y-%m-%d", jst) + f" ({WEEK[jst.tm_wday]})")
        self.set("utc", "UTC " + time.strftime("%H:%M:%S", time.gmtime(now)))
        self.set("host", f"{info.get('host') or '--'}   {info.get('ip') or '--'}")

        carrier = bool(st and st.get("carrier"))
        frame = st.get("frame") if st else None
        same_minute = bool(st and st.get("minute") == minute_now)
        sig = emulate.at(frame if same_minute else None, now, carrier)

        # 状態の表示
        sync = (st or {}).get("sync") or {}
        if st is None:
            badge, text, color = "#3a434c", "jjyd 応答なし", DIM
            l1, l2 = "状態ファイルがない、または更新が止まっている", self.status_path
        elif carrier:
            badge, text, color = "#16442a", f"送信中   {st.get('khz', 0)} kHz", OK
            l1, l2 = self._sync_lines(sync)
        else:
            badge, text, color = "#4a1d1d", "停止(キャリア OFF)", BAD
            l1, l2 = self._sync_lines(sync)
            l1 = "時刻が合っていないため送信しない。 " + l1
        self.cv.itemconfigure(self.items["badge"], fill=badge)
        self.set("state", text, color)
        self.set("sync1", l1)
        self.set("sync2", l2)

        for name in ("d1", "d2", "d3"):
            on = getattr(sig, name) if st else False
            self.cv.itemconfigure(self.items[name], fill=LED_ON[name] if on else LED_OFF[name])
        lines = emulate.lcd_lines(frame if same_minute else None, now, carrier, st.get("khz", 60)) if st else ("", "")
        for row, line in enumerate(lines):
            for col in range(16):
                self.set(f"lcd{row}_{col}", line[col] if col < len(line) else " ")
        rise, fall = (st or {}).get("rise_ms"), (st or {}).get("fall_ms")
        if carrier and rise is not None and fall is not None:
            self.set("edge", f"直近の実測({st['idx']} 秒目): 立ち上がり 秒頭 +{rise:.2f} ms / 立ち下がり {fall:.1f} ms"
                              f" → 高レベル {fall - rise:.1f} ms")
        else:
            self.set("edge", "")

        self._update_frame(st if same_minute else None, st, carrier, sig)
        self.wave_carrier = carrier
        self._update_wave(now, sig)
        self._update_chrony(now, info)

    @staticmethod
    def _sync_lines(sync: dict) -> tuple[str, str]:
        if not sync:
            return "時刻源: --", ""
        src = "RTC" if sync.get("mode") == "rtc" else "NTP"
        now_s = "chrony は同期済み" if sync.get("synced") else "chrony は未同期"
        age = sync.get("age_s")
        return (f"{now_s}({src} モード)",
                f"最後に同期を確認してから {fmt_dur(age)} / 保持できる時間 {fmt_dur(sync.get('limit_s'))}")

    def _update_frame(self, st_same, st, carrier, sig) -> None:
        frame = (st or {}).get("frame") if carrier else None
        key = (frame, sig.idx if st_same else None, carrier)
        if key == self.grid_key:
            return
        self.grid_key = key
        cv = self.cv
        self.set("minute", (st.get("minute") + " JST") if frame and st else "--", TEXT if frame else DIM)
        n = len(frame) if frame else 60
        call = fr.is_callsign(frame)
        lay = fr.layout(call)
        cur_i = sig.idx if st_same is not None else None
        for i, (r, t, num, wl, bar) in enumerate(self.cells):
            if i == 60:
                st_ = "normal" if n > 60 else "hidden"
                for it in (r, t, num, wl, bar):
                    cv.itemconfigure(it, state=st_)
            field, wlabel = lay[i]
            sym = frame[i] if frame and i < len(frame) else None
            cv.itemconfigure(bar, fill=fr.COLOR[field] if frame else EDGE)
            cv.itemconfigure(wl, text=wlabel, fill=fr.COLOR[field] if frame else DIM)
            if sym is None:
                cv.itemconfigure(r, fill=CELL, outline=EDGE, width=1)
                cv.itemconfigure(t, text="-", fill=EDGE)
                continue
            cur = cur_i == i
            past = cur_i is not None and i < cur_i
            cv.itemconfigure(r, fill=SYM_COLOR[sym] if cur else SYM_DARK[sym] if past else CELL,
                             outline="#ffffff" if cur else EDGE, width=3 if cur else 1)
            cv.itemconfigure(t, text=sym, fill="#10161c" if cur else SYM_COLOR[sym] if not past else TEXT)
            cv.itemconfigure(num, fill="#10161c" if cur else DIM)
            if cur:
                cv.itemconfigure(wl, fill="#10161c")
        self._update_legend(frame, call, lay, cur_i)

    def _update_legend(self, frame, call, lay, cur_i) -> None:
        """右の表: 項目ごとの意味と、今のフレームが表している値。今の秒が属する項目の行を強調する。"""
        d = fr.decode(frame) if frame else {}
        here = lay[cur_i][0] if cur_i in lay else None
        ok = lambda b: "OK" if b else "NG"  # noqa: E731
        ls = d.get("ls")
        text = {
            "min": f"{d['min']:02d} 分" if d else "--",
            "hour": f"{d['hour']:02d} 時" if d else "--",
            "doy": f"{d['doy']} 日目" if d else "--",
            "year": ("送らない" if d["year"] is None else f"{d['year']} 年") if d else "--",
            "wday": ("送らない" if d["wday"] is None else f"{'日月火水木金土'[d['wday']]}曜") if d else "--",
            "par": f"PA1 {ok(d['pa1_ok'])} / PA2 {ok(d['pa2_ok'])}" if d else "--",
            "su": ("なし" if not any(d["su"]) else "あり") if d else "--",
            "ls": "--" if not d else "送らない" if ls is None else "なし" if not ls[0] else "挿入予告" if ls[1] else "削除予告",
            "res": "0" if d else "--",
            "mk": "7 か所" if d else "--",
            "call": "JJY を送信中" if call else "なし",
            "st": ("なし" if not any(d["st"]) else "あり") if call else "なし",
        }
        for key, bg in self.legend:
            self.set("lg_" + key, text[key], TEXT if d and (key not in ("call", "st") or call) else DIM)
            self.cv.itemconfigure(bg, fill=CELL if key == here else PANEL)

    def _update_wave(self, now: float, sig) -> None:
        """直近 WAVE_S 秒の波形。秒ごとの記録(シンボルと送信中か)から、変化の位置を正確に計算して描く(標本点をつなぐのではない)。"""
        sec = int(now // 1)
        if sig.sym is not None or sec not in self.secs:
            self.secs[sec] = (sig.sym, sig.idx, self.wave_carrier)
        for old in [t for t in self.secs if t < sec - WAVE_S - 2]:
            del self.secs[old]
        t0 = now - WAVE_S
        x0, x1 = self.s(self.wx0), self.s(self.wx1)
        scale = (x1 - x0) / WAVE_S
        lanes = (("amp", 1), ("d1", 2), ("d2", 3))
        pts = {name: [] for name, _ in lanes}
        for t_sec in range(int(t0 // 1), sec + 1):
            sym, idx, car = self.secs.get(t_sec, (None, 0, False))
            for off, amp, d1, d2 in emulate.segments(sym, idx, car):
                t = t_sec + off
                if t > now:
                    break
                x = x0 + (max(t, t0) - t0) * scale
                for name, v in (("amp", amp), ("d1", 1.0 if d1 else 0.0), ("d2", 1.0 if d2 else 0.0)):
                    p = pts[name]
                    if p:
                        p += [x, p[-1]]  # 階段状: 前の値のまま変化の位置まで進めてから、新しい値へ
                    p += [x, self._lane_y(name, v)]
        for name, _ in lanes:
            p = pts[name]
            if len(p) >= 2:
                p += [x1, p[-1]]  # 現在(右端)まで
            if len(p) >= 4:
                self.cv.coords(self.items["w_" + name], *p)
        first = int(t0 // 1) + 1
        for i, (ln, tx) in enumerate(self.grid_lines):
            t = first + i
            x = x0 + (t - t0) * scale
            if x < x0 or x > x1:
                self.cv.coords(ln, -10, -10, -10, -10)
                self.cv.coords(tx, -100, -100)
                continue
            self.cv.coords(ln, x, self.s(self.lanes["amp"][0]), x, self.s(self.lanes["d2"][1]))
            self.cv.coords(tx, x, self.s(764))
            label = str(t % 60)
            if self.cache.get(("g", tx)) != label:  # 文字の描画は重い(Pi では 1 個ごとに数 ms)ので、変わったときだけ
                self.cache[("g", tx)] = label
                self.cv.itemconfigure(tx, text=label)

    def _lane_y(self, name: str, v: float) -> float:
        top, bot = self.lanes[name]
        return self.s(bot - 6 - v * (bot - top - 12))

    def _update_chrony(self, now: float, info: dict) -> None:
        t = info.get("tracking")
        if t:
            self.set("t_ref", f"{t['ref'] or t['refid']} (st {t['stratum']})"[:30])
            self.set("t_off", fmt_ms(t["offset"]), OK if abs(t["offset"]) <= 0.25 else BAD)
            self.set("t_rms", fmt_ms(t["rms"], False))
            self.set("t_freq", f"{t['freq_ppm']:+.3f} ppm")
            self.set("t_upd", fmt_dur(now - t["ref_time"]) + "前")
            self.set("t_leap", t["leap"], OK if t["leap"] == "Normal" else WARN)
        else:
            for k in self.rows_n:
                self.set("t_" + k, "--", DIM)
        self.set("src_head", "S 時刻源                   st 間隔 reach 受信   ずれ      誤差", None)
        srcs = info.get("sources") or []
        for i in range(6):
            if i < len(srcs):
                r = srcs[i]
                line = (f"{r['state']} {r['name'][:24]:<24} {r['stratum']:>2} {2 ** r['poll']:>4} {r['reach']:>5o} "
                        f"{r['last_rx']:>4}s {r['offset'] * 1000:>+8.2f}ms {r['error'] * 1000:>6.1f}ms")
                self.set(f"src{i}", line, OK if r["state"] == "*" else TEXT if r["state"] == "+" else DIM)
            else:
                self.set(f"src{i}", "")
        sv = info.get("services") or {}
        for u in ("jjyd", "chrony"):
            v = sv.get(u)
            self.set("y_" + u, v or "--", OK if v == "active" else BAD if v else DIM)
        temp = info.get("temp_c")
        self.set("y_temp", "--" if temp is None else f"{temp:.1f} °C", DIM if temp is None else BAD if temp >= 80 else WARN if temp >= 70 else TEXT)
        load = info.get("load")
        self.set("y_load", "--" if load is None else f"{load:.2f}")
        self.set("y_up", fmt_dur(info.get("uptime_s")))


def main() -> None:
    ap = argparse.ArgumentParser(description="JJY/タイムサーバの画面モニタ")
    ap.add_argument("--status", default="/run/jjyd/status.json", help="jjyd の状態ファイル")
    ap.add_argument("--windowed", action="store_true", help="全画面にせず 1280x720 の窓で開く")
    args = ap.parse_args()
    root = tk.Tk()
    root.title("JJY monitor")
    root.configure(bg=BG)
    full = {"on": not args.windowed}
    if args.windowed:
        root.geometry("1280x720")
    else:
        root.attributes("-fullscreen", True)

    def toggle(_e=None):
        full["on"] = not full["on"]
        root.attributes("-fullscreen", full["on"])

    root.bind("<Escape>", lambda _e: root.destroy())
    root.bind("<F11>", toggle)
    Monitor(root, args.status)
    root.mainloop()
