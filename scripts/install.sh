#!/bin/sh
# Raspberry Pi OS (Bookworm) 上で root として実行: sudo ./scripts/install.sh
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)

apt-get update
apt-get install -y chrony python3-gpiozero python3-lgpio

# 他のNTPクライアントと競合しないように
systemctl disable --now systemd-timesyncd 2>/dev/null || true

# PWM0 を GPIO18 に出す
CFG=/boot/firmware/config.txt
grep -q '^dtoverlay=pwm,pin=18,func=2' "$CFG" || echo 'dtoverlay=pwm,pin=18,func=2' >> "$CFG"
# I2C(RTC と LCD で使用)を有効化
grep -q '^dtparam=i2c_arm=on' "$CFG" || echo 'dtparam=i2c_arm=on' >> "$CFG"
# アナログ音声出力は PWM を使うため、同じ PWM ブロックを使うキャリアと衝突する。無効化する。
sed -i 's/^dtparam=audio=on/dtparam=audio=off/' "$CFG"

mkdir -p /opt/timeserver
cp -r "$ROOT/server" /opt/timeserver/
install -m 644 "$ROOT/server/config/timeserver.conf" /etc/chrony/conf.d/timeserver.conf
[ -f /etc/jjyd.toml ] || install -m 644 "$ROOT/server/config/jjyd.toml" /etc/jjyd.toml
install -m 644 "$ROOT/server/systemd/jjyd.service" /etc/systemd/system/jjyd.service

# 基板上の DS3231 RTC を有効化する。RTC 未実装の基板なら JJY_RTC=0 で実行: sudo JJY_RTC=0 ./scripts/install.sh
if [ "${JJY_RTC:-1}" = "1" ]; then
    grep -q '^dtoverlay=i2c-rtc,ds3231' "$CFG" || echo 'dtoverlay=i2c-rtc,ds3231' >> "$CFG"
    apt-get remove -y fake-hwclock || true
    systemctl disable fake-hwclock 2>/dev/null || true
    # RTC からの時刻設定を udev に任せる (Raspberry Pi OS 標準手順)
    sed -i '/^if \[ -e \/run\/systemd\/system \]/,/^fi/ s/^/#/' /lib/udev/hwclock-set 2>/dev/null || true
    sed -i '/^\[rtc\]/,/^\[/ s/^enabled = false/enabled = true/' /etc/jjyd.toml 2>/dev/null || true
else
    sed -i '/^\[rtc\]/,/^\[/ s/^enabled = true/enabled = false/' /etc/jjyd.toml 2>/dev/null || true
    # RTC が無いと、起動時の時計は保存された時刻から始まる。systemd-timesyncd を止めると保存が止まるので、fake-hwclock で
    # 1 時間ごとと停止時に保存して、起動直後のずれを縮める(chrony が同期するまでの間の時計)。RTC がある構成では不要。
    apt-get install -y fake-hwclock
    systemctl enable fake-hwclock 2>/dev/null || true
    fake-hwclock save || true
fi

systemctl daemon-reload
systemctl enable --now chrony
systemctl restart chrony
systemctl enable jjyd
echo "インストール完了。PWMオーバーレイ反映のため再起動してください: sudo reboot"
