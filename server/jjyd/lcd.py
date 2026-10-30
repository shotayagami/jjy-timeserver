"""I2C 接続の 16x2 文字 LCD(ST7032 系: AQM1602 など、3.3V、アドレス 0x3E)の表示。

追加の依存ライブラリは使わず、Linux の /dev/i2c-N を直接叩く。書き込み専用(このLCDは読み出し不可)。
"""
import logging
import time
from datetime import datetime

log = logging.getLogger("jjyd.lcd")

I2C_SLAVE = 0x0703
LINE_ADDR = (0x00, 0x40)  # DDRAM アドレス: 1行目 / 2行目
WIDTH = 16


class LinuxI2C:
    def __init__(self, bus: int, address: int):
        import fcntl
        import os

        self._os = os
        self.fd = os.open(f"/dev/i2c-{bus}", os.O_RDWR)
        fcntl.ioctl(self.fd, I2C_SLAVE, address)

    def write(self, data: bytes) -> None:
        self._os.write(self.fd, bytes(data))

    def close(self) -> None:
        self._os.close(self.fd)


def format_lines(dt: datetime, khz: int, state: str) -> tuple[str, str]:
    """1行目: 日付と曜日 / 2行目: 時刻・送信周波数・状態(TX=送信中, OFF=停止)。各16文字に揃える。"""
    line1 = dt.strftime("%Y-%m-%d %a")
    line2 = f"{dt.strftime('%H:%M:%S')} {khz}k {state}"
    return line1[:WIDTH].ljust(WIDTH), line2[:WIDTH].ljust(WIDTH)


class Lcd:
    """ST7032 の初期化(3.3V 内蔵昇圧)と 2 行表示。contrast は 0〜63(表示が薄い/濃いときに調整)。"""

    def __init__(self, bus, contrast: int = 32, sleep=time.sleep):
        self.bus = bus
        self.sleep = sleep
        c = max(0, min(63, contrast))
        for cmd, wait in ((0x38, 0.001), (0x39, 0.001), (0x14, 0.001), (0x70 | (c & 0x0F), 0.001),
                          (0x56 | ((c >> 4) & 0x03), 0.001), (0x6C, 0.25), (0x38, 0.001), (0x0C, 0.001),
                          (0x01, 0.002)):
            self._cmd(cmd)
            self.sleep(wait)

    def _cmd(self, cmd: int) -> None:
        self.bus.write(bytes([0x00, cmd]))

    def _line(self, row: int, text: str) -> None:
        self._cmd(0x80 | LINE_ADDR[row])
        self.bus.write(bytes([0x40]) + text.encode("ascii", "replace")[:WIDTH])

    def show(self, line1: str, line2: str) -> None:
        self._line(0, line1)
        self._line(1, line2)

    def close(self) -> None:
        try:
            self.show("".ljust(WIDTH), "".ljust(WIDTH))
            self.bus.close()
        except Exception:  # 終了時なので握りつぶす
            pass


class DryRunLcd:
    def show(self, line1: str, line2: str) -> None:
        log.info("LCD |%s|%s|", line1, line2)

    def close(self) -> None:
        pass
