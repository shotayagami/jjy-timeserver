"""拡張基板の制御。

- キャリア: カーネルの sysfs PWM (GPIO18 / PWM0) で 40kHz or 60kHz の50%デューティ矩形波
- 帯域:     GPIO26 (任意)。High=40kHz / Low=60kHz の共振コンデンサ切替
- 振幅:     GPIO23 (74LVC125 の OE、アクティブLow)。ON=最大振幅 / OFF=約10%
"""
import logging
import time
from pathlib import Path

log = logging.getLogger("jjyd.tx")


class Transmitter:
    def __init__(self, khz: int, pwm_chip: int, pwm_channel: int, level_gpio: int,
                 select_gpio: int | None = None):
        from gpiozero import DigitalOutputDevice  # Pi 以外では import しない

        self.freq_hz = khz * 1000
        base = Path(f"/sys/class/pwm/pwmchip{pwm_chip}")
        self.pwm = base / f"pwm{pwm_channel}"
        if not self.pwm.exists():
            (base / "export").write_text(str(pwm_channel))
            for _ in range(50):  # udev による権限設定待ち
                if (self.pwm / "enable").exists():
                    break
                time.sleep(0.05)
        # active_high=False: on() で Low = 74LVC125 の B ゲートを有効化 = 最大振幅
        self.level_dev = DigitalOutputDevice(level_gpio, active_high=False, initial_value=False)
        # 帯域切替: High でフォトモスリレーが共振コンデンサを追加し 40kHz に同調。Low(既定)は 60kHz。
        self.select_dev = None
        if select_gpio is not None:
            self.select_dev = DigitalOutputDevice(select_gpio, initial_value=(khz == 40))
        self.carrier_on = False
        self.set_carrier(False)

    def _w(self, name: str, value) -> None:
        (self.pwm / name).write_text(str(value))

    def set_carrier(self, on: bool) -> None:
        if on:
            period = round(1e9 / self.freq_hz)
            self._w("enable", 0)
            self._w("duty_cycle", 0)
            self._w("period", period)
            self._w("duty_cycle", period // 2)
            self._w("enable", 1)
        else:
            self.level(False)
            self._w("enable", 0)
        self.carrier_on = on

    def level(self, full: bool) -> None:
        self.level_dev.value = 1 if full else 0

    def close(self) -> None:
        try:
            self.set_carrier(False)
        finally:
            self.level_dev.close()
            if self.select_dev is not None:
                self.select_dev.close()


class DryRunTransmitter:
    """ハードウェア無しでタイミングだけ確認するためのダミー。"""

    def __init__(self):
        self.carrier_on = False

    def set_carrier(self, on: bool) -> None:
        self.carrier_on = on
        log.info("carrier %s", "ON" if on else "OFF")

    def level(self, full: bool) -> None:
        t = time.time_ns()
        log.info("level %-4s  at +%.3f s", "FULL" if full else "LOW", (t % 1_000_000_000) / 1e9)

    def close(self) -> None:
        pass
